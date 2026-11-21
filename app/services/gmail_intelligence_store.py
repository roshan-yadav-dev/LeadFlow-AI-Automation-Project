import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings
from app.models.gmail import GmailIntelligenceResult

logger = logging.getLogger("leadflow")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GmailIntelligenceStore:
    def __init__(self, database_file: str):
        self.database_file = database_file
        Path(database_file).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        try:
            os.chmod(database_file, 0o600)
        except OSError:
            logger.warning("Could not set Gmail intelligence database permissions")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_file, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS gmail_message_intelligence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    lead_id TEXT,
                    received_timestamp TEXT NOT NULL DEFAULT '',
                    match_status TEXT NOT NULL,
                    ignore_reason TEXT,
                    classification_status TEXT NOT NULL DEFAULT 'PENDING',
                    intent_category TEXT,
                    sentiment TEXT,
                    confidence REAL,
                    summary TEXT,
                    extracted_information TEXT NOT NULL DEFAULT '{}',
                    action_items TEXT NOT NULL DEFAULT '[]',
                    suggested_next_step TEXT,
                    analysis_error TEXT,
                    analyzed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS gmail_intelligence_analysis_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    classification_status TEXT NOT NULL,
                    analysis_error TEXT,
                    result_json TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(gmail_message_intelligence)"
                ).fetchall()
            }
            if "received_timestamp" not in columns:
                connection.execute(
                    "ALTER TABLE gmail_message_intelligence "
                    "ADD COLUMN received_timestamp TEXT NOT NULL DEFAULT ''"
                )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_gmail_intelligence_lead
                ON gmail_message_intelligence(lead_id)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_gmail_intelligence_match_status
                ON gmail_message_intelligence(match_status)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_gmail_intelligence_analysis_status
                ON gmail_message_intelligence(classification_status)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_gmail_intelligence_intent
                ON gmail_message_intelligence(intent_category)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_gmail_intelligence_sentiment
                ON gmail_message_intelligence(sentiment)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_gmail_intelligence_history_message
                ON gmail_intelligence_analysis_history(message_id, created_at)
                """
            )

    def record_match(
        self,
        message_id: str,
        lead_id: str | None,
        match_status: str,
        ignore_reason: str | None = None,
        received_timestamp: str = "",
    ) -> None:
        now = _utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT lead_id, match_status, classification_status
                FROM gmail_message_intelligence
                WHERE message_id = ?
                """,
                (message_id,),
            ).fetchone()
            unchanged_match = (
                row is not None
                and row["lead_id"] == lead_id
                and row["match_status"] == match_status
            )
            if row is None:
                connection.execute(
                    """
                    INSERT INTO gmail_message_intelligence (
                        message_id, lead_id, received_timestamp, match_status,
                        ignore_reason,
                        classification_status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        lead_id,
                        received_timestamp,
                        match_status,
                        ignore_reason,
                        "PENDING" if match_status == "MATCHED" else "SKIPPED",
                        now,
                        now,
                    ),
                )
            elif unchanged_match:
                connection.execute(
                    """
                    UPDATE gmail_message_intelligence
                    SET ignore_reason = ?, received_timestamp = ?,
                        updated_at = ?
                    WHERE message_id = ?
                    """,
                    (ignore_reason, received_timestamp, now, message_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE gmail_message_intelligence
                    SET lead_id = ?, received_timestamp = ?, match_status = ?,
                        ignore_reason = ?,
                        classification_status = ?, intent_category = NULL,
                        sentiment = NULL, confidence = NULL, summary = NULL,
                        extracted_information = '{}', action_items = '[]',
                        suggested_next_step = NULL, analysis_error = NULL,
                        analyzed_at = NULL, updated_at = ?
                    WHERE message_id = ?
                    """,
                    (
                        lead_id,
                        received_timestamp,
                        match_status,
                        ignore_reason,
                        "PENDING" if match_status == "MATCHED" else "SKIPPED",
                        now,
                        message_id,
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, message_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM gmail_message_intelligence
                WHERE message_id = ?
                """,
                (message_id,),
            ).fetchone()
        return self._decode_row(row) if row else None

    def list_analysis_candidates(
        self,
        limit: int,
        force_reanalysis: bool = False,
    ) -> list[dict]:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=15)
        ).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE gmail_message_intelligence
                SET classification_status = 'PENDING',
                    analysis_error = 'Previous analysis was interrupted; retry is available.',
                    updated_at = ?
                WHERE classification_status = 'ANALYZING'
                  AND updated_at < ?
                """,
                (_utc_now(), cutoff),
            )
            statuses = ["PENDING", "FAILED"]
            if force_reanalysis:
                statuses.extend(["SUCCESS", "SKIPPED"])
            placeholders = ",".join("?" for _ in statuses)
            rows = connection.execute(
                f"""
                SELECT * FROM gmail_message_intelligence
                WHERE match_status = 'MATCHED'
                  AND classification_status IN ({placeholders})
                ORDER BY created_at, message_id
                LIMIT ?
                """,
                [*statuses, limit],
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def claim_analysis(
        self,
        message_id: str,
        force_reanalysis: bool = False,
    ) -> bool:
        statuses = ["PENDING", "FAILED"]
        if force_reanalysis:
            statuses.extend(["SUCCESS", "SKIPPED"])
        placeholders = ",".join("?" for _ in statuses)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                f"""
                UPDATE gmail_message_intelligence
                SET classification_status = 'ANALYZING',
                    analysis_error = NULL, updated_at = ?
                WHERE message_id = ?
                  AND match_status = 'MATCHED'
                  AND classification_status IN ({placeholders})
                """,
                [_utc_now(), message_id, *statuses],
            )
            connection.commit()
            return cursor.rowcount == 1
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_analysis(
        self,
        message_id: str,
        result: GmailIntelligenceResult,
    ) -> None:
        now = _utc_now()
        result_data = result.model_dump(mode="json")
        result_json = json.dumps(result_data, ensure_ascii=False)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE gmail_message_intelligence
                SET classification_status = 'SUCCESS',
                    intent_category = ?, sentiment = ?, confidence = ?,
                    summary = ?, extracted_information = ?, action_items = ?,
                    suggested_next_step = ?, analysis_error = NULL,
                    analyzed_at = ?, updated_at = ?
                WHERE message_id = ? AND classification_status = 'ANALYZING'
                """,
                (
                    result.intent_category,
                    result.sentiment,
                    result.confidence,
                    result.summary,
                    json.dumps(
                        result.extracted_information.model_dump(mode="json"),
                        ensure_ascii=False,
                    ),
                    json.dumps(result.action_items, ensure_ascii=False),
                    result.suggested_next_step,
                    now,
                    now,
                    message_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Analysis claim is no longer active")
            connection.execute(
                """
                INSERT INTO gmail_intelligence_analysis_history (
                    message_id, classification_status, result_json, created_at
                ) VALUES (?, 'SUCCESS', ?, ?)
                """,
                (message_id, result_json, now),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_analysis_failure(self, message_id: str, safe_error: str) -> None:
        now = _utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE gmail_message_intelligence
                SET classification_status = 'FAILED',
                    analysis_error = ?, updated_at = ?
                WHERE message_id = ? AND classification_status = 'ANALYZING'
                """,
                (safe_error, now, message_id),
            )
            if cursor.rowcount == 1:
                connection.execute(
                    """
                    INSERT INTO gmail_intelligence_analysis_history (
                        message_id, classification_status,
                        analysis_error, created_at
                    ) VALUES (?, 'FAILED', ?, ?)
                    """,
                    (message_id, safe_error, now),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_analysis_skipped(self, message_id: str, reason: str) -> None:
        now = _utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE gmail_message_intelligence
                SET classification_status = 'SKIPPED',
                    analysis_error = ?, updated_at = ?
                WHERE message_id = ? AND classification_status = 'ANALYZING'
                """,
                (reason, now, message_id),
            )
            if cursor.rowcount == 1:
                connection.execute(
                    """
                    INSERT INTO gmail_intelligence_analysis_history (
                        message_id, classification_status,
                        analysis_error, created_at
                    ) VALUES (?, 'SKIPPED', ?, ?)
                    """,
                    (message_id, reason, now),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_analysis_history(self, message_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT classification_status, analysis_error, result_json,
                       created_at
                FROM gmail_intelligence_analysis_history
                WHERE message_id = ?
                ORDER BY id
                """,
                (message_id,),
            ).fetchall()
        return [
            {
                "classification_status": row["classification_status"],
                "analysis_error": row["analysis_error"],
                "result": (
                    json.loads(row["result_json"])
                    if row["result_json"]
                    else None
                ),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def list_by_lead(
        self,
        lead_id: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        with self._connect() as connection:
            total = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM gmail_message_intelligence
                    WHERE lead_id = ? AND match_status = 'MATCHED'
                    """,
                    (lead_id,),
                ).fetchone()[0]
            )
            rows = connection.execute(
                """
                SELECT * FROM gmail_message_intelligence
                WHERE lead_id = ? AND match_status = 'MATCHED'
                ORDER BY received_timestamp DESC, message_id DESC
                LIMIT ? OFFSET ?
                """,
                (lead_id, limit, offset),
            ).fetchall()
        return [self._decode_row(row) for row in rows], total

    def latest_message_timestamp_for_lead(self, lead_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT MAX(received_timestamp)
                FROM gmail_message_intelligence
                WHERE lead_id = ? AND match_status = 'MATCHED'
                """,
                (lead_id,),
            ).fetchone()
        return row[0] or None

    def overview_counts(self) -> dict:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT match_status, classification_status, intent_category,
                       sentiment, COUNT(*) AS count
                FROM gmail_message_intelligence
                GROUP BY match_status, classification_status,
                         intent_category, sentiment
                """
            ).fetchall()

        counts = {
            "matched": 0,
            "unmatched": 0,
            "ignored": 0,
            "ambiguous": 0,
            "analyzed": 0,
            "pending": 0,
            "failed": 0,
            "intents": {},
            "sentiments": {},
        }
        for row in rows:
            count = row["count"]
            match_status = row["match_status"].lower()
            if match_status in counts:
                counts[match_status] += count
            status = row["classification_status"]
            if status == "SUCCESS":
                counts["analyzed"] += count
            elif status == "PENDING":
                counts["pending"] += count
            elif status == "FAILED":
                counts["failed"] += count
            if status == "SUCCESS" and row["intent_category"]:
                key = row["intent_category"]
                counts["intents"][key] = counts["intents"].get(key, 0) + count
            if status == "SUCCESS" and row["sentiment"]:
                key = row["sentiment"]
                counts["sentiments"][key] = (
                    counts["sentiments"].get(key, 0) + count
                )
        return counts

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> dict:
        result = dict(row)
        result["extracted_information"] = json.loads(
            result["extracted_information"] or "{}"
        )
        result["action_items"] = json.loads(result["action_items"] or "[]")
        return result


gmail_intelligence_store = GmailIntelligenceStore(
    settings.GMAIL_INTELLIGENCE_DB_FILE
)
