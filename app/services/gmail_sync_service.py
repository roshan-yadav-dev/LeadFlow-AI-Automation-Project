import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services.gmail_inbox_service import fetch_gmail_messages

logger = logging.getLogger("leadflow")


class GmailInboxStore:
    def __init__(self, database_file: str):
        self.database_file = database_file
        Path(database_file).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        try:
            os.chmod(database_file, 0o600)
        except OSError:
            logger.warning("Could not set Gmail database permissions")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_file, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS gmail_messages (
                    message_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL DEFAULT '',
                    sender_email TEXT NOT NULL DEFAULT '',
                    sender_name TEXT NOT NULL DEFAULT '',
                    recipient_email TEXT NOT NULL DEFAULT '',
                    subject TEXT NOT NULL DEFAULT '',
                    received_timestamp TEXT NOT NULL DEFAULT '',
                    internal_date INTEGER NOT NULL DEFAULT 0,
                    snippet TEXT NOT NULL DEFAULT '',
                    text_body TEXT NOT NULL DEFAULT '',
                    html_body TEXT NOT NULL DEFAULT '',
                    headers TEXT NOT NULL DEFAULT '{}',
                    labels TEXT NOT NULL DEFAULT '[]',
                    unread INTEGER NOT NULL DEFAULT 1,
                    stored_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS gmail_sync_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_gmail_internal_date
                ON gmail_messages(internal_date)
                """
            )
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(gmail_messages)"
                ).fetchall()
            }
            if "headers" not in columns:
                connection.execute(
                    "ALTER TABLE gmail_messages "
                    "ADD COLUMN headers TEXT NOT NULL DEFAULT '{}'"
                )

    def add_message(self, message: dict) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO gmail_messages (
                    message_id, thread_id, sender_email, sender_name,
                    recipient_email, subject, received_timestamp,
                    internal_date, snippet, text_body, html_body, headers,
                    labels, unread, stored_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message["message_id"],
                    message.get("thread_id", ""),
                    message.get("sender_email", ""),
                    message.get("sender_name", ""),
                    message.get("recipient_email", ""),
                    message.get("subject", ""),
                    message.get("received_timestamp", ""),
                    int(message.get("internal_date") or 0),
                    message.get("snippet", ""),
                    message.get("text_body", ""),
                    message.get("html_body", ""),
                    json.dumps(message.get("headers") or {}),
                    json.dumps(message.get("labels") or []),
                    1 if message.get("unread") else 0,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return cursor.rowcount == 1

    def get_message(self, message_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM gmail_messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
        return self._row_to_message(row) if row else None

    def list_messages_for_intelligence(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT message_id, thread_id, sender_email, sender_name,
                       recipient_email, subject, received_timestamp,
                       internal_date, snippet, text_body, html_body,
                       headers, labels, unread
                FROM gmail_messages
                ORDER BY internal_date DESC, message_id DESC
                """
            ).fetchall()
        return [self._row_to_message(row) for row in rows]

    def get_message_metadata_by_ids(self, message_ids: list[str]) -> dict[str, dict]:
        if not message_ids:
            return {}
        placeholders = ",".join("?" for _ in message_ids)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT message_id, sender_email, sender_name, subject,
                       received_timestamp, snippet
                FROM gmail_messages
                WHERE message_id IN ({placeholders})
                """,
                message_ids,
            ).fetchall()
        return {row["message_id"]: dict(row) for row in rows}

    def count_messages(self) -> int:
        with self._connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM gmail_messages"
                ).fetchone()[0]
            )

    def list_messages(
        self,
        page: int,
        page_size: int,
        unread: bool | None = None,
        sender: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        search: str | None = None,
    ) -> dict:
        clauses: list[str] = []
        parameters: list[object] = []

        if unread is not None:
            clauses.append("unread = ?")
            parameters.append(1 if unread else 0)
        if sender:
            clauses.append(
                "(sender_email LIKE ? OR sender_name LIKE ?)"
            )
            pattern = f"%{sender}%"
            parameters.extend([pattern, pattern])
        if date_from:
            clauses.append("received_timestamp >= ?")
            parameters.append(date_from)
        if date_to:
            clauses.append("received_timestamp <= ?")
            parameters.append(date_to)
        if search:
            clauses.append(
                "(subject LIKE ? OR sender_email LIKE ? OR sender_name LIKE ?)"
            )
            pattern = f"%{search}%"
            parameters.extend([pattern, pattern, pattern])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM gmail_messages {where}",
                parameters,
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT * FROM gmail_messages {where}
                ORDER BY internal_date DESC, message_id DESC
                LIMIT ? OFFSET ?
                """,
                [*parameters, page_size, (page - 1) * page_size],
            ).fetchall()

        return {
            "messages": [self._row_to_message(row) for row in rows],
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    def get_checkpoint(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM gmail_sync_state WHERE key = 'last_sync_timestamp'",
            ).fetchone()
        return int(row[0]) if row else 0

    def set_checkpoint(self, timestamp: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO gmail_sync_state(key, value)
                VALUES('last_sync_timestamp', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(timestamp),),
            )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> dict:
        labels = json.loads(row["labels"]) if row["labels"] else []
        if not isinstance(labels, list):
            labels = []
        headers = (
            json.loads(row["headers"])
            if "headers" in row.keys() and row["headers"]
            else {}
        )
        if not isinstance(headers, dict):
            headers = {}
        return {
            "message_id": row["message_id"],
            "thread_id": row["thread_id"],
            "sender_email": row["sender_email"],
            "sender_name": row["sender_name"],
            "recipient_email": row["recipient_email"],
            "subject": row["subject"],
            "received_timestamp": row["received_timestamp"],
            "internal_date": row["internal_date"],
            "snippet": row["snippet"],
            "text_body": row["text_body"],
            "html_body": row["html_body"],
            "headers": headers,
            "labels": labels,
            "unread": bool(row["unread"]),
        }


gmail_store = GmailInboxStore(settings.GMAIL_DB_FILE)
sync_lock = threading.Lock()
_scheduler_task: asyncio.Task | None = None


def sync_inbox() -> dict:
    if not sync_lock.acquire(blocking=False):
        return {
            "status": "running",
            "messages_fetched": 0,
            "new_messages": 0,
            "duplicates_skipped": 0,
            "error": None,
        }

    try:
        checkpoint = gmail_store.get_checkpoint()
        after_timestamp = int(checkpoint / 1000) if checkpoint else None

        for attempt in range(2):
            try:
                messages, fetched_count = fetch_gmail_messages(
                    max_results=settings.GMAIL_SYNC_BATCH_SIZE,
                    after_timestamp=after_timestamp,
                    max_pages=settings.GMAIL_SYNC_MAX_PAGES,
                )
                break
            except Exception:
                if attempt == 0:
                    time.sleep(2)
                    continue
                raise

        new_count = 0
        duplicate_count = 0
        maximum_timestamp = checkpoint
        for message in messages:
            if gmail_store.add_message(message):
                new_count += 1
            else:
                duplicate_count += 1
            maximum_timestamp = max(
                maximum_timestamp,
                int(message.get("internal_date") or 0),
            )

        if maximum_timestamp > checkpoint:
            gmail_store.set_checkpoint(maximum_timestamp)

        logger.info(
            "Gmail sync completed: fetched=%d new=%d duplicates=%d",
            fetched_count,
            new_count,
            duplicate_count,
        )
        return {
            "status": "success",
            "messages_fetched": fetched_count,
            "new_messages": new_count,
            "duplicates_skipped": duplicate_count,
            "error": None,
        }
    except Exception as exc:
        logger.exception("Gmail synchronization failed")
        return {
            "status": "error",
            "messages_fetched": 0,
            "new_messages": 0,
            "duplicates_skipped": 0,
            "error": "Temporary Gmail synchronization failure",
        }
    finally:
        sync_lock.release()


async def _sync_scheduler() -> None:
    interval = max(settings.GMAIL_SYNC_INTERVAL_SECONDS, 30)
    while True:
        await asyncio.sleep(interval)
        if settings.GMAIL_SYNC_ENABLED:
            await asyncio.to_thread(sync_inbox)


async def start_sync_scheduler() -> None:
    global _scheduler_task
    if settings.GMAIL_SYNC_ENABLED:
        _scheduler_task = asyncio.create_task(_sync_scheduler())
        logger.info("Gmail inbox synchronization scheduler started")


async def stop_sync_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        _scheduler_task = None
