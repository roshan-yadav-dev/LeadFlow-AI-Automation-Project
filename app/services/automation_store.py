import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.models.automation import to_kolkata_iso

logger = logging.getLogger("leadflow")


class AutomationError(Exception):
    """Base exception for automation domain."""
    pass


class DuplicateIdempotencyKeyError(AutomationError):
    """Raised when an operation with a duplicate idempotency key is attempted."""
    pass


class EntityNotFoundError(AutomationError):
    """Raised when a requested automation entity is not found."""
    pass


class InvalidStateError(AutomationError):
    """Raised when an action is performed on an entity in an invalid state."""
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class AutomationStore:
    def __init__(self, database_file: str):
        self.database_file = database_file
        Path(database_file).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()
        try:
            os.chmod(database_file, 0o600)
        except OSError:
            logger.warning("Could not set automation database permissions")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_file, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")

            # 1. Lead Scores
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS lead_scores (
                    id TEXT PRIMARY KEY,
                    lead_id TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    tier TEXT NOT NULL,
                    factors TEXT NOT NULL DEFAULT '{}',
                    version TEXT NOT NULL DEFAULT 'v1',
                    idempotency_key TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lead_scores_lead
                ON lead_scores(lead_id, created_at DESC)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lead_scores_tier
                ON lead_scores(tier)
                """
            )

            # 2. Follow-Up Tasks
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS follow_up_tasks (
                    id TEXT PRIMARY KEY,
                    lead_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    scheduled_for TEXT NOT NULL,
                    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
                    priority TEXT NOT NULL DEFAULT 'MEDIUM',
                    status TEXT NOT NULL DEFAULT 'SCHEDULED',
                    channel TEXT NOT NULL DEFAULT 'EMAIL',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    completed_at TEXT DEFAULT NULL,
                    idempotency_key TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_lead_status
                ON follow_up_tasks(lead_id, status)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_scheduled
                ON follow_up_tasks(scheduled_for, status)
                """
            )

            # 3. Reminders
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    lead_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    remind_at TEXT NOT NULL,
                    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    recipient TEXT NOT NULL DEFAULT '',
                    channel TEXT NOT NULL DEFAULT 'INTERNAL_LOG',
                    idempotency_key TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES follow_up_tasks(id) ON DELETE SET NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_reminders_lead_status
                ON reminders(lead_id, status)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_reminders_remind_at
                ON reminders(remind_at, status)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_reminders_task
                ON reminders(task_id)
                """
            )

            # 4. Workflow Rules
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_rules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    conditions TEXT NOT NULL DEFAULT '{}',
                    actions TEXT NOT NULL DEFAULT '[]',
                    requires_approval INTEGER NOT NULL DEFAULT 1,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rules_trigger
                ON workflow_rules(trigger_type, is_active)
                """
            )

            # 5. Workflow Executions
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_executions (
                    id TEXT PRIMARY KEY,
                    rule_id TEXT NOT NULL,
                    lead_id TEXT NOT NULL,
                    trigger_event TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    context_data TEXT NOT NULL DEFAULT '{}',
                    result_data TEXT DEFAULT NULL,
                    error_message TEXT DEFAULT NULL,
                    idempotency_key TEXT UNIQUE,
                    started_at TEXT DEFAULT NULL,
                    completed_at TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (rule_id) REFERENCES workflow_rules(id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_executions_lead
                ON workflow_executions(lead_id, status)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_executions_rule
                ON workflow_executions(rule_id)
                """
            )

            # 6. Approval Requests
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_requests (
                    id TEXT PRIMARY KEY,
                    workflow_execution_id TEXT DEFAULT NULL,
                    lead_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_payload TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    requested_by TEXT NOT NULL DEFAULT 'system',
                    reviewed_by TEXT DEFAULT NULL,
                    reviewed_at TEXT DEFAULT NULL,
                    rejection_reason TEXT DEFAULT NULL,
                    expires_at TEXT DEFAULT NULL,
                    idempotency_key TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (workflow_execution_id) REFERENCES workflow_executions(id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_approvals_lead_status
                ON approval_requests(lead_id, status)
                """
            )

            # 7. Automation Audit Logs
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_audit_logs (
                    id TEXT PRIMARY KEY,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    lead_id TEXT DEFAULT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT 'system',
                    details TEXT NOT NULL DEFAULT '{}',
                    ip_address TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_logs_entity
                ON automation_audit_logs(entity_type, entity_id)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_logs_lead
                ON automation_audit_logs(lead_id)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_logs_created
                ON automation_audit_logs(created_at DESC)
                """
            )

            # 8. Background Automation Jobs
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    scheduled_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_retries INTEGER NOT NULL DEFAULT 3,
                    locked_until TEXT DEFAULT NULL,
                    last_error TEXT DEFAULT NULL,
                    idempotency_key TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_status_scheduled
                ON automation_jobs(status, scheduled_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_locked
                ON automation_jobs(locked_until)
                """
            )

            # 9. Lead Submissions (Form Intake & Idempotency)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS lead_submissions (
                    submission_id TEXT PRIMARY KEY,
                    form_id TEXT DEFAULT NULL,
                    lead_id TEXT DEFAULT NULL,
                    email TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    processing_status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error_message TEXT NOT NULL DEFAULT '',
                    email_status TEXT NOT NULL DEFAULT 'PENDING'
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_submissions_email
                ON lead_submissions(email)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_submissions_status
                ON lead_submissions(processing_status)
                """
            )

            # 10. Email Drafts (Controlled Outbound Email Delivery)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS email_drafts (
                    id TEXT PRIMARY KEY,
                    lead_id TEXT NOT NULL,
                    submission_id TEXT DEFAULT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    html_body TEXT DEFAULT NULL,
                    preferred_contact TEXT NOT NULL DEFAULT 'email',
                    consent INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    approval_id TEXT DEFAULT NULL,
                    approved_by TEXT DEFAULT NULL,
                    approved_at TEXT DEFAULT NULL,
                    sent_at TEXT DEFAULT NULL,
                    sent_by TEXT DEFAULT NULL,
                    gmail_message_id TEXT DEFAULT NULL,
                    gmail_thread_id TEXT DEFAULT NULL,
                    error_message TEXT DEFAULT NULL,
                    error_code TEXT DEFAULT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    idempotency_key TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (approval_id) REFERENCES approval_requests(id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_email_drafts_lead
                ON email_drafts(lead_id)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_email_drafts_status
                ON email_drafts(status)
                """
            )

            # Additive Migrations: check and add missing columns
            task_cols = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(follow_up_tasks)").fetchall()
            }
            if "completed_at" not in task_cols:
                connection.execute("ALTER TABLE follow_up_tasks ADD COLUMN completed_at TEXT DEFAULT NULL")

            appr_cols = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(approval_requests)").fetchall()
            }
            if "expires_at" not in appr_cols:
                connection.execute("ALTER TABLE approval_requests ADD COLUMN expires_at TEXT DEFAULT NULL")

            rule_cols = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(workflow_rules)").fetchall()
            }
            if "is_deleted" not in rule_cols:
                connection.execute("ALTER TABLE workflow_rules ADD COLUMN is_deleted INTEGER NOT NULL DEFAULT 0")

            sub_cols = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(lead_submissions)").fetchall()
            }
            if "email_status" not in sub_cols:
                connection.execute("ALTER TABLE lead_submissions ADD COLUMN email_status TEXT NOT NULL DEFAULT 'PENDING'")

            # Recover any orphaned processing jobs back to pending on startup
            connection.execute(
                """
                UPDATE automation_jobs
                SET status = 'PENDING', locked_until = NULL
                WHERE status = 'PROCESSING'
                """
            )

    # --- 1. Lead Scores ---
    def create_lead_score(
        self,
        lead_id: str,
        score: int,
        tier: str,
        factors: dict[str, Any] | None = None,
        version: str = "v2-deterministic",
        idempotency_key: str | None = None,
    ) -> dict:
        now = _utc_now()
        record_id = _generate_id("score")
        factors_json = json.dumps(factors or {})

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO lead_scores (
                        id, lead_id, score, tier, factors, version,
                        idempotency_key, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        lead_id,
                        score,
                        tier,
                        factors_json,
                        version,
                        idempotency_key,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if idempotency_key and "idempotency_key" in str(exc).lower():
                raise DuplicateIdempotencyKeyError(
                    f"Duplicate idempotency key '{idempotency_key}'"
                ) from exc
            raise

        return self.get_lead_score_by_id(record_id)  # type: ignore

    def get_lead_score_by_id(self, score_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM lead_scores WHERE id = ?", (score_id,)
            ).fetchone()
        return self._row_to_score(row) if row else None

    def get_latest_lead_score(self, lead_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM lead_scores
                WHERE lead_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (lead_id,),
            ).fetchone()
        return self._row_to_score(row) if row else None

    def list_lead_score_history(self, lead_id: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM lead_scores
                WHERE lead_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (lead_id,),
            ).fetchall()
        return [self._row_to_score(row) for row in rows]

    def get_lead_leaderboard(
        self,
        limit: int = 50,
        tier: str | None = None,
    ) -> list[dict]:
        """
        Return ranked leads ordered by their latest score DESC.
        """
        where_clause = "WHERE tier = ?" if tier else ""
        params: list[Any] = [tier] if tier else []
        params.append(limit)

        sql = f"""
            WITH ranked_scores AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY lead_id
                           ORDER BY created_at DESC, id DESC
                       ) as rn
                FROM lead_scores
            )
            SELECT * FROM ranked_scores
            WHERE rn = 1
            {"AND tier = ?" if tier else ""}
            ORDER BY score DESC, created_at DESC
            LIMIT ?
        """
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._row_to_score(row) for row in rows]

    def _row_to_score(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "lead_id": row["lead_id"],
            "score": row["score"],
            "tier": row["tier"],
            "factors": json.loads(row["factors"] or "{}"),
            "version": row["version"],
            "idempotency_key": row["idempotency_key"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # --- 2. Follow-Up Tasks ---
    def create_follow_up_task(
        self,
        lead_id: str,
        title: str,
        scheduled_for: str,
        description: str = "",
        timezone_str: str = "Asia/Kolkata",
        priority: str = "MEDIUM",
        channel: str = "EMAIL",
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        now = _utc_now()
        task_id = _generate_id("task")
        metadata_json = json.dumps(metadata or {})

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO follow_up_tasks (
                        id, lead_id, title, description, scheduled_for,
                        timezone, priority, status, channel, metadata,
                        completed_at, idempotency_key, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'SCHEDULED', ?, ?, NULL, ?, ?, ?)
                    """,
                    (
                        task_id,
                        lead_id,
                        title,
                        description,
                        scheduled_for,
                        timezone_str,
                        priority,
                        channel,
                        metadata_json,
                        idempotency_key,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if idempotency_key and "idempotency_key" in str(exc).lower():
                raise DuplicateIdempotencyKeyError(
                    f"Duplicate idempotency key '{idempotency_key}'"
                ) from exc
            raise

        return self.get_follow_up_task(task_id)  # type: ignore

    def get_follow_up_task(self, task_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM follow_up_tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return self._row_to_task(row) if row else None

    def update_follow_up_task(
        self,
        task_id: str,
        status: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        scheduled_for: str | None = None,
        timezone_str: str | None = None,
        metadata: dict[str, Any] | None = None,
        completed: bool = False,
    ) -> dict | None:
        task = self.get_follow_up_task(task_id)
        if not task:
            return None

        clauses: list[str] = ["updated_at = ?"]
        now = _utc_now()
        params: list[Any] = [now]

        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if description is not None:
            clauses.append("description = ?")
            params.append(description)
        if priority is not None:
            clauses.append("priority = ?")
            params.append(priority)
        if scheduled_for is not None:
            clauses.append("scheduled_for = ?")
            params.append(scheduled_for)
        if timezone_str is not None:
            clauses.append("timezone = ?")
            params.append(timezone_str)
        if metadata is not None:
            clauses.append("metadata = ?")
            params.append(json.dumps(metadata))
        if completed or status == "COMPLETED":
            clauses.append("completed_at = ?")
            params.append(now)

        params.append(task_id)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE follow_up_tasks SET {', '.join(clauses)} WHERE id = ?",
                params,
            )
        return self.get_follow_up_task(task_id)

    def reschedule_task(
        self,
        task_id: str,
        new_scheduled_for: str,
        timezone_str: str | None = None,
    ) -> dict | None:
        now = _utc_now()
        clauses = ["scheduled_for = ?", "updated_at = ?"]
        params: list[Any] = [new_scheduled_for, now]
        if timezone_str:
            clauses.append("timezone = ?")
            params.append(timezone_str)
        params.append(task_id)

        with self._connect() as connection:
            connection.execute(
                f"UPDATE follow_up_tasks SET {', '.join(clauses)} WHERE id = ?",
                params,
            )
        return self.get_follow_up_task(task_id)

    def complete_task(self, task_id: str) -> dict | None:
        return self.update_follow_up_task(task_id, status="COMPLETED", completed=True)

    def cancel_task(self, task_id: str) -> dict | None:
        return self.update_follow_up_task(task_id, status="CANCELLED")

    def list_follow_up_tasks(
        self,
        lead_id: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        channel: str | None = None,
        upcoming_only: bool = False,
        overdue_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses = []
        params: list[Any] = []
        now = _utc_now()

        if lead_id:
            clauses.append("lead_id = ?")
            params.append(lead_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if priority:
            clauses.append("priority = ?")
            params.append(priority)
        if channel:
            clauses.append("channel = ?")
            params.append(channel)

        if upcoming_only:
            clauses.append("status IN ('SCHEDULED', 'IN_PROGRESS')")
            clauses.append("scheduled_for >= ?")
            params.append(now)
        elif overdue_only:
            clauses.append("status IN ('SCHEDULED', 'IN_PROGRESS')")
            clauses.append("scheduled_for < ?")
            params.append(now)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM follow_up_tasks
            {where_sql}
            ORDER BY scheduled_for ASC, id ASC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_task(row) for row in rows]

    def list_upcoming_tasks(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self.list_follow_up_tasks(upcoming_only=True, limit=limit, offset=offset)

    def list_overdue_tasks(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self.list_follow_up_tasks(overdue_only=True, limit=limit, offset=offset)

    def _row_to_task(self, row: sqlite3.Row) -> dict:
        row_keys = row.keys()
        scheduled_for = row["scheduled_for"]
        return {
            "id": row["id"],
            "lead_id": row["lead_id"],
            "title": row["title"],
            "description": row["description"],
            "scheduled_for": scheduled_for,
            "scheduled_for_local": to_kolkata_iso(scheduled_for) if scheduled_for else "",
            "timezone": row["timezone"],
            "priority": row["priority"],
            "status": row["status"],
            "channel": row["channel"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "idempotency_key": row["idempotency_key"],
            "completed_at": row["completed_at"] if "completed_at" in row_keys else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # --- 3. Reminders ---
    def create_reminder(
        self,
        lead_id: str,
        title: str,
        remind_at: str,
        task_id: str | None = None,
        timezone_str: str = "Asia/Kolkata",
        recipient: str = "",
        channel: str = "INTERNAL_LOG",
        idempotency_key: str | None = None,
    ) -> dict:
        now = _utc_now()
        reminder_id = _generate_id("rem")

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO reminders (
                        id, task_id, lead_id, title, remind_at,
                        timezone, status, recipient, channel,
                        idempotency_key, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?)
                    """,
                    (
                        reminder_id,
                        task_id,
                        lead_id,
                        title,
                        remind_at,
                        timezone_str,
                        recipient,
                        channel,
                        idempotency_key,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if idempotency_key and "idempotency_key" in str(exc).lower():
                raise DuplicateIdempotencyKeyError(
                    f"Duplicate idempotency key '{idempotency_key}'"
                ) from exc
            raise

        return self.get_reminder(reminder_id)  # type: ignore

    def get_reminder(self, reminder_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
            ).fetchone()
        return self._row_to_reminder(row) if row else None

    def update_reminder_status(self, reminder_id: str, status: str) -> dict | None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE reminders SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, reminder_id),
            )
        return self.get_reminder(reminder_id)

    def dismiss_reminder(self, reminder_id: str) -> dict | None:
        return self.update_reminder_status(reminder_id, "DISMISSED")

    def list_reminders(
        self,
        lead_id: str | None = None,
        task_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses = []
        params: list[Any] = []
        if lead_id:
            clauses.append("lead_id = ?")
            params.append(lead_id)
        if task_id:
            clauses.append("task_id = ?")
            params.append(task_id)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM reminders
            {where_sql}
            ORDER BY remind_at ASC, id ASC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_reminder(row) for row in rows]

    def list_pending_reminders(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self.list_reminders(status="PENDING", limit=limit, offset=offset)

    def list_completed_reminders(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self.list_reminders(status="SENT", limit=limit, offset=offset)

    def _row_to_reminder(self, row: sqlite3.Row) -> dict:
        remind_at = row["remind_at"]
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "lead_id": row["lead_id"],
            "title": row["title"],
            "remind_at": remind_at,
            "remind_at_local": to_kolkata_iso(remind_at) if remind_at else "",
            "timezone": row["timezone"],
            "status": row["status"],
            "recipient": row["recipient"],
            "channel": row["channel"],
            "idempotency_key": row["idempotency_key"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # --- 4. Workflow Rules ---
    def create_workflow_rule(
        self,
        name: str,
        trigger_type: str,
        conditions: dict[str, Any] | None = None,
        actions: list[dict[str, Any]] | None = None,
        requires_approval: bool = True,
        is_active: bool = True,
    ) -> dict:
        now = _utc_now()
        rule_id = _generate_id("rule")
        conditions_json = json.dumps(conditions or {})
        actions_json = json.dumps(actions or [])

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflow_rules (
                    id, name, trigger_type, conditions, actions,
                    requires_approval, is_active, is_deleted, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    rule_id,
                    name,
                    trigger_type,
                    conditions_json,
                    actions_json,
                    1 if requires_approval else 0,
                    1 if is_active else 0,
                    now,
                    now,
                ),
            )
        return self.get_workflow_rule(rule_id)  # type: ignore

    def get_workflow_rule(self, rule_id: str, include_deleted: bool = False) -> dict | None:
        query = "SELECT * FROM workflow_rules WHERE id = ?"
        if not include_deleted:
            query += " AND is_deleted = 0"
        with self._connect() as connection:
            row = connection.execute(query, (rule_id,)).fetchone()
        return self._row_to_rule(row) if row else None

    def update_workflow_rule(
        self,
        rule_id: str,
        name: str | None = None,
        conditions: dict[str, Any] | None = None,
        actions: list[dict[str, Any]] | None = None,
        requires_approval: bool | None = None,
        is_active: bool | None = None,
    ) -> dict | None:
        rule = self.get_workflow_rule(rule_id)
        if not rule:
            return None

        now = _utc_now()
        clauses = ["updated_at = ?"]
        params: list[Any] = [now]

        if name is not None:
            clauses.append("name = ?")
            params.append(name)
        if conditions is not None:
            clauses.append("conditions = ?")
            params.append(json.dumps(conditions))
        if actions is not None:
            clauses.append("actions = ?")
            params.append(json.dumps(actions))
        if requires_approval is not None:
            clauses.append("requires_approval = ?")
            params.append(1 if requires_approval else 0)
        if is_active is not None:
            clauses.append("is_active = ?")
            params.append(1 if is_active else 0)

        params.append(rule_id)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE workflow_rules SET {', '.join(clauses)} WHERE id = ? AND is_deleted = 0",
                params,
            )
        return self.get_workflow_rule(rule_id)

    def delete_workflow_rule(self, rule_id: str) -> bool:
        """
        Soft-delete workflow rule.
        Preserves all historical workflow executions, approval requests, and audit logs.
        """
        now = _utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE workflow_rules
                SET is_deleted = 1, is_active = 0, updated_at = ?
                WHERE id = ? AND is_deleted = 0
                """,
                (now, rule_id),
            )
            return cursor.rowcount > 0

    def list_workflow_rules(
        self,
        trigger_type: str | None = None,
        is_active: bool | None = None,
    ) -> list[dict]:
        clauses = ["is_deleted = 0"]
        params: list[Any] = []
        if trigger_type:
            clauses.append("trigger_type = ?")
            params.append(trigger_type)
        if is_active is not None:
            clauses.append("is_active = ?")
            params.append(1 if is_active else 0)

        where_sql = f"WHERE {' AND '.join(clauses)}"
        query = f"SELECT * FROM workflow_rules {where_sql} ORDER BY created_at ASC"

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_rule(row) for row in rows]

    def list_active_rules_for_trigger(self, trigger_type: str) -> list[dict]:
        return self.list_workflow_rules(trigger_type=trigger_type, is_active=True)

    def _row_to_rule(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "trigger_type": row["trigger_type"],
            "conditions": json.loads(row["conditions"] or "{}"),
            "actions": json.loads(row["actions"] or "[]"),
            "requires_approval": bool(row["requires_approval"]),
            "is_active": bool(row["is_active"]),
            "is_deleted": bool(row["is_deleted"]) if "is_deleted" in row.keys() else False,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # --- 5. Workflow Executions ---
    def create_workflow_execution(
        self,
        rule_id: str,
        lead_id: str,
        trigger_event: str,
        status: str = "PENDING",
        context_data: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        now = _utc_now()
        exec_id = _generate_id("exec")
        context_json = json.dumps(context_data or {})

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO workflow_executions (
                        id, rule_id, lead_id, trigger_event, status,
                        context_data, idempotency_key, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        exec_id,
                        rule_id,
                        lead_id,
                        trigger_event,
                        status,
                        context_json,
                        idempotency_key,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if idempotency_key and "idempotency_key" in str(exc).lower():
                raise DuplicateIdempotencyKeyError(
                    f"Duplicate idempotency key '{idempotency_key}'"
                ) from exc
            raise

        return self.get_workflow_execution(exec_id)  # type: ignore

    def get_workflow_execution(self, execution_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workflow_executions WHERE id = ?", (execution_id,)
            ).fetchone()
        return self._row_to_execution(row) if row else None

    def update_workflow_execution(
        self,
        execution_id: str,
        status: str | None = None,
        result_data: dict[str, Any] | None = None,
        error_message: str | None = None,
        started: bool = False,
        completed: bool = False,
    ) -> dict | None:
        now = _utc_now()
        clauses = ["updated_at = ?"]
        params: list[Any] = [now]

        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if result_data is not None:
            clauses.append("result_data = ?")
            params.append(json.dumps(result_data))
        if error_message is not None:
            clauses.append("error_message = ?")
            params.append(error_message)
        if started:
            clauses.append("started_at = ?")
            params.append(now)
        if completed:
            clauses.append("completed_at = ?")
            params.append(now)

        params.append(execution_id)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE workflow_executions SET {', '.join(clauses)} WHERE id = ?",
                params,
            )
        return self.get_workflow_execution(execution_id)

    def list_workflow_executions(
        self,
        lead_id: str | None = None,
        rule_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses = []
        params: list[Any] = []
        if lead_id:
            clauses.append("lead_id = ?")
            params.append(lead_id)
        if rule_id:
            clauses.append("rule_id = ?")
            params.append(rule_id)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM workflow_executions
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_execution(row) for row in rows]

    def _row_to_execution(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "rule_id": row["rule_id"],
            "lead_id": row["lead_id"],
            "trigger_event": row["trigger_event"],
            "status": row["status"],
            "context_data": json.loads(row["context_data"] or "{}"),
            "result_data": (
                json.loads(row["result_data"]) if row["result_data"] else None
            ),
            "error_message": row["error_message"],
            "idempotency_key": row["idempotency_key"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # --- 6. Approval Requests ---
    def create_approval_request(
        self,
        lead_id: str,
        action_type: str,
        action_payload: dict[str, Any] | None = None,
        workflow_execution_id: str | None = None,
        requested_by: str = "system",
        expires_at: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        now = _utc_now()
        appr_id = _generate_id("appr")
        payload_json = json.dumps(action_payload or {})

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO approval_requests (
                        id, workflow_execution_id, lead_id, action_type,
                        action_payload, status, requested_by, expires_at,
                        idempotency_key, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?)
                    """,
                    (
                        appr_id,
                        workflow_execution_id,
                        lead_id,
                        action_type,
                        payload_json,
                        requested_by,
                        expires_at,
                        idempotency_key,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if idempotency_key and "idempotency_key" in str(exc).lower():
                raise DuplicateIdempotencyKeyError(
                    f"Duplicate idempotency key '{idempotency_key}'"
                ) from exc
            raise

        return self.get_approval_request(appr_id)  # type: ignore

    def get_approval_request(self, approval_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM approval_requests WHERE id = ?", (approval_id,)
            ).fetchone()
        return self._row_to_approval(row) if row else None

    def record_approval_decision(
        self,
        approval_id: str,
        action: str,
        reviewed_by: str,
        rejection_reason: str | None = None,
    ) -> dict | None:
        now = _utc_now()
        status = "APPROVED" if action == "APPROVE" else "REJECTED"
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE approval_requests
                SET status = ?, reviewed_by = ?, reviewed_at = ?,
                    rejection_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, reviewed_by, now, rejection_reason, now, approval_id),
            )
        return self.get_approval_request(approval_id)

    def expire_stale_approvals(self, max_age_hours: int = 72) -> list[dict]:
        """
        Expire approvals that are PENDING and past expires_at or older than max_age_hours.
        Also marks linked executions as FAILED.
        """
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        cutoff_iso = (now_dt - timedelta(hours=max_age_hours)).isoformat()

        expired_list: list[dict] = []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM approval_requests
                WHERE status = 'PENDING'
                  AND (
                      created_at <= ?
                      OR (expires_at IS NOT NULL AND expires_at <= ?)
                  )
                """,
                (cutoff_iso, now_iso),
            ).fetchall()

            for row in rows:
                appr_id = row["id"]
                connection.execute(
                    """
                    UPDATE approval_requests
                    SET status = 'EXPIRED', rejection_reason = 'Approval request expired without review',
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now_iso, appr_id),
                )
                exec_id = row["workflow_execution_id"]
                if exec_id:
                    connection.execute(
                        """
                        UPDATE workflow_executions
                        SET status = 'FAILED', error_message = 'Approval request expired without review',
                            completed_at = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (now_iso, now_iso, exec_id),
                    )
                expired_list.append(self._row_to_approval(row))

        return expired_list

    def list_approval_requests(
        self,
        status: str | None = None,
        lead_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if lead_id:
            clauses.append("lead_id = ?")
            params.append(lead_id)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM approval_requests
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_approval(row) for row in rows]

    def _row_to_approval(self, row: sqlite3.Row) -> dict:
        row_keys = row.keys()
        return {
            "id": row["id"],
            "workflow_execution_id": row["workflow_execution_id"],
            "lead_id": row["lead_id"],
            "action_type": row["action_type"],
            "action_payload": json.loads(row["action_payload"] or "{}"),
            "status": row["status"],
            "requested_by": row["requested_by"],
            "reviewed_by": row["reviewed_by"],
            "reviewed_at": row["reviewed_at"],
            "rejection_reason": row["rejection_reason"],
            "expires_at": row["expires_at"] if "expires_at" in row_keys else None,
            "idempotency_key": row["idempotency_key"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # --- 7. Automation Audit Logs ---
    def record_audit_log(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        lead_id: str | None = None,
        actor: str = "system",
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> str:
        now = _utc_now()
        log_id = _generate_id("audit")
        details_json = json.dumps(details or {})

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO automation_audit_logs (
                    id, entity_type, entity_id, lead_id, action,
                    actor, details, ip_address, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    entity_type,
                    entity_id,
                    lead_id,
                    action,
                    actor,
                    details_json,
                    ip_address,
                    now,
                ),
            )
        return log_id

    def list_audit_logs(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        lead_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses = []
        params: list[Any] = []
        if entity_type:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if entity_id:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if lead_id:
            clauses.append("lead_id = ?")
            params.append(lead_id)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM automation_audit_logs
            {where_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_audit(row) for row in rows]

    def _row_to_audit(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "lead_id": row["lead_id"],
            "action": row["action"],
            "actor": row["actor"],
            "details": json.loads(row["details"] or "{}"),
            "ip_address": row["ip_address"],
            "created_at": row["created_at"],
        }

    # --- 8. Automation Jobs (Persistent Background Processing) ---
    def enqueue_job(
        self,
        job_type: str,
        payload: dict[str, Any] | None = None,
        scheduled_at: str | None = None,
        max_retries: int = 3,
        idempotency_key: str | None = None,
    ) -> dict:
        now = _utc_now()
        job_id = _generate_id("job")
        scheduled_time = scheduled_at or now
        payload_json = json.dumps(payload or {})

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO automation_jobs (
                        id, job_type, payload, scheduled_at, status,
                        attempts, max_retries, locked_until, last_error,
                        idempotency_key, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'PENDING', 0, ?, NULL, NULL, ?, ?, ?)
                    """,
                    (
                        job_id,
                        job_type,
                        payload_json,
                        scheduled_time,
                        max_retries,
                        idempotency_key,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if idempotency_key and "idempotency_key" in str(exc).lower():
                raise DuplicateIdempotencyKeyError(
                    f"Duplicate job idempotency key '{idempotency_key}'"
                ) from exc
            raise

        return self.get_job(job_id)  # type: ignore

    def get_job(self, job_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM automation_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._row_to_job(row) if row else None

    def claim_due_jobs(
        self,
        batch_size: int = 10,
        lock_duration_seconds: int = 60,
    ) -> list[dict]:
        """
        Atomically claim due pending or expired locked jobs.
        Prevents duplicate execution and handles crash recovery.
        """
        now = _utc_now()
        now_dt = datetime.now(timezone.utc)
        lock_until = (now_dt + timedelta(seconds=lock_duration_seconds)).isoformat()

        claimed_jobs: list[dict] = []
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT id FROM automation_jobs
                WHERE (status = 'PENDING' AND scheduled_at <= ?)
                   OR (status = 'PROCESSING' AND locked_until IS NOT NULL AND locked_until < ?)
                ORDER BY scheduled_at ASC
                LIMIT ?
                """,
                (now, now, batch_size),
            ).fetchall()

            if not rows:
                connection.execute("COMMIT")
                return []

            job_ids = [row["id"] for row in rows]
            placeholders = ",".join("?" for _ in job_ids)

            connection.execute(
                f"""
                UPDATE automation_jobs
                SET status = 'PROCESSING',
                    locked_until = ?,
                    attempts = attempts + 1,
                    updated_at = ?
                WHERE id IN ({placeholders})
                """,
                [lock_until, now, *job_ids],
            )

            updated_rows = connection.execute(
                f"SELECT * FROM automation_jobs WHERE id IN ({placeholders})",
                job_ids,
            ).fetchall()
            claimed_jobs = [self._row_to_job(row) for row in updated_rows]
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            logger.exception("Failed to claim due automation jobs")
            raise
        finally:
            connection.close()

        return claimed_jobs

    def complete_job(self, job_id: str, result: dict[str, Any] | None = None) -> bool:
        now = _utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE automation_jobs
                SET status = 'COMPLETED', locked_until = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, job_id),
            )
            return cursor.rowcount > 0

    def fail_job(
        self,
        job_id: str,
        error: str,
        retry: bool = True,
    ) -> bool:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        job = self.get_job(job_id)
        if not job:
            return False

        attempts = job["attempts"]
        max_retries = job["max_retries"]

        if retry and attempts < max_retries:
            # Exponential backoff: min(300, 10 * 2^(attempts-1))
            delay_seconds = min(300, 10 * (2 ** max(0, attempts - 1)))
            next_schedule = (now_dt + timedelta(seconds=delay_seconds)).isoformat()
            new_status = "PENDING"
        else:
            next_schedule = job["scheduled_at"]
            new_status = "FAILED"

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE automation_jobs
                SET status = ?, scheduled_at = ?, locked_until = NULL,
                    last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_status, next_schedule, error, now, job_id),
            )
            return cursor.rowcount > 0

    def list_jobs(
        self,
        status: str | None = None,
        job_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if job_type:
            clauses.append("job_type = ?")
            params.append(job_type)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM automation_jobs
            {where_sql}
            ORDER BY scheduled_at ASC, id ASC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_job(row) for row in rows]

    def _row_to_job(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "job_type": row["job_type"],
            "payload": json.loads(row["payload"] or "{}"),
            "scheduled_at": row["scheduled_at"],
            "status": row["status"],
            "attempts": row["attempts"],
            "max_retries": row["max_retries"],
            "locked_until": row["locked_until"],
            "last_error": row["last_error"],
            "idempotency_key": row["idempotency_key"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # --- 9. Lead Submissions (Form Intake & Idempotency) ---
    def create_lead_submission(
        self,
        submission_id: str,
        email: str,
        payload_hash: str,
        form_id: str | None = None,
        lead_id: str | None = None,
        processing_status: str = "PENDING",
        error_message: str = "",
        email_status: str = "PENDING",
    ) -> dict:
        now = _utc_now()
        normalized_email = email.strip().lower()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO lead_submissions (
                        submission_id, form_id, lead_id, email, payload_hash,
                        processing_status, created_at, updated_at, error_message,
                        email_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        submission_id,
                        form_id,
                        lead_id,
                        normalized_email,
                        payload_hash,
                        processing_status,
                        now,
                        now,
                        error_message,
                        email_status,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "primary key" in str(exc).lower() or "submission_id" in str(exc).lower():
                raise DuplicateIdempotencyKeyError(
                    f"Duplicate submission ID '{submission_id}'"
                ) from exc
            raise

        return self.get_lead_submission(submission_id)  # type: ignore

    def get_lead_submission(self, submission_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM lead_submissions WHERE submission_id = ?",
                (submission_id,),
            ).fetchone()
        return self._row_to_submission(row) if row else None

    def update_lead_submission(
        self,
        submission_id: str,
        processing_status: str,
        lead_id: str | None = None,
        error_message: str | None = None,
        email_status: str | None = None,
    ) -> bool:
        now = _utc_now()
        updates = ["processing_status = ?", "updated_at = ?"]
        params: list[Any] = [processing_status, now]

        if lead_id is not None:
            updates.append("lead_id = ?")
            params.append(lead_id)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if email_status is not None:
            updates.append("email_status = ?")
            params.append(email_status)

        params.append(submission_id)
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE lead_submissions SET {', '.join(updates)} WHERE submission_id = ?",
                params,
            )
            return cursor.rowcount > 0

    def list_lead_submissions(
        self,
        email: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses = []
        params: list[Any] = []
        if email:
            clauses.append("email = ?")
            params.append(email.strip().lower())
        if status:
            clauses.append("processing_status = ?")
            params.append(status)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM lead_submissions
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_submission(row) for row in rows]

    def _row_to_submission(self, row: sqlite3.Row) -> dict:
        row_keys = row.keys()
        return {
            "submission_id": row["submission_id"],
            "form_id": row["form_id"],
            "lead_id": row["lead_id"],
            "email": row["email"],
            "payload_hash": row["payload_hash"],
            "processing_status": row["processing_status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "error_message": row["error_message"],
            "email_status": row["email_status"] if "email_status" in row_keys else "PENDING",
        }

    # --- 10. Email Drafts ---
    def _row_to_email_draft(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "lead_id": row["lead_id"],
            "submission_id": row["submission_id"],
            "recipient": row["recipient"],
            "subject": row["subject"],
            "body": row["body"],
            "html_body": row["html_body"],
            "preferred_contact": row["preferred_contact"],
            "consent": bool(row["consent"]),
            "status": row["status"],
            "approval_id": row["approval_id"],
            "approved_by": row["approved_by"],
            "approved_at": row["approved_at"],
            "sent_at": row["sent_at"],
            "sent_by": row["sent_by"],
            "gmail_message_id": row["gmail_message_id"],
            "gmail_thread_id": row["gmail_thread_id"],
            "error_message": row["error_message"],
            "error_code": row["error_code"],
            "retry_count": row["retry_count"],
            "idempotency_key": row["idempotency_key"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create_email_draft(
        self,
        lead_id: str,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        preferred_contact: str = "email",
        consent: bool = True,
        status: str = "PENDING",
        submission_id: str | None = None,
        approval_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        draft_id = _generate_id("draft")
        now = _utc_now()
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO email_drafts (
                        id, lead_id, submission_id, recipient, subject, body,
                        html_body, preferred_contact, consent, status, approval_id,
                        idempotency_key, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        draft_id,
                        lead_id,
                        submission_id,
                        recipient.strip().lower(),
                        subject.strip(),
                        body.strip(),
                        html_body,
                        preferred_contact.strip().lower(),
                        1 if consent else 0,
                        status,
                        approval_id,
                        idempotency_key,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if idempotency_key and "unique" in str(exc).lower():
                    row = connection.execute(
                        "SELECT * FROM email_drafts WHERE idempotency_key = ?",
                        (idempotency_key,),
                    ).fetchone()
                    if row:
                        return self._row_to_email_draft(row)
                    raise DuplicateIdempotencyKeyError(
                        f"Duplicate email draft idempotency key: '{idempotency_key}'"
                    ) from exc
                raise
        return self.get_email_draft(draft_id)  # type: ignore

    def get_email_draft(self, draft_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM email_drafts WHERE id = ?",
                (draft_id,),
            ).fetchone()
        return self._row_to_email_draft(row) if row else None

    def get_email_draft_by_approval_id(self, approval_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM email_drafts WHERE approval_id = ? ORDER BY created_at DESC LIMIT 1",
                (approval_id,),
            ).fetchone()
        return self._row_to_email_draft(row) if row else None

    def list_email_drafts(
        self,
        lead_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses = []
        params: list[Any] = []
        if lead_id:
            clauses.append("lead_id = ?")
            params.append(lead_id.strip())
        if status:
            clauses.append("status = ?")
            params.append(status.strip().upper())

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT * FROM email_drafts
            {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_email_draft(r) for r in rows]

    def count_email_drafts(
        self,
        lead_id: str | None = None,
        status: str | None = None,
    ) -> int:
        clauses = []
        params: list[Any] = []
        if lead_id:
            clauses.append("lead_id = ?")
            params.append(lead_id.strip())
        if status:
            clauses.append("status = ?")
            params.append(status.strip().upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT COUNT(*) FROM email_drafts {where}"
        with self._connect() as connection:
            return int(connection.execute(query, params).fetchone()[0])

    def update_email_draft(self, draft_id: str, **kwargs) -> dict:
        now = _utc_now()
        allowed = {
            "status",
            "approval_id",
            "approved_by",
            "approved_at",
            "sent_at",
            "sent_by",
            "gmail_message_id",
            "gmail_thread_id",
            "error_message",
            "error_code",
            "retry_count",
            "subject",
            "body",
            "html_body",
            "recipient",
            "preferred_contact",
            "consent",
        }
        updates = ["updated_at = ?"]
        params: list[Any] = [now]
        for k, v in kwargs.items():
            if k in allowed:
                updates.append(f"{k} = ?")
                params.append(v)
        params.append(draft_id)
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE email_drafts SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            if cursor.rowcount == 0:
                raise EntityNotFoundError(f"Email draft '{draft_id}' not found")
        return self.get_email_draft(draft_id)  # type: ignore

    def record_email_draft_approved(self, draft_id: str, approved_by: str) -> dict:
        now = _utc_now()
        return self.update_email_draft(
            draft_id,
            status="APPROVED",
            approved_by=approved_by,
            approved_at=now,
            error_message=None,
            error_code=None,
        )

    def record_email_draft_sent(
        self,
        draft_id: str,
        gmail_message_id: str,
        gmail_thread_id: str | None,
        sent_by: str,
    ) -> dict:
        now = _utc_now()
        return self.update_email_draft(
            draft_id,
            status="SENT",
            sent_at=now,
            sent_by=sent_by,
            gmail_message_id=gmail_message_id,
            gmail_thread_id=gmail_thread_id,
            error_message=None,
            error_code=None,
        )

    def record_email_draft_failed(
        self,
        draft_id: str,
        error_message: str,
        error_code: str | None = None,
    ) -> dict:
        return self.update_email_draft(
            draft_id,
            status="FAILED",
            error_message=error_message,
            error_code=error_code,
        )

    # --- Overview Counts ---
    def get_overview_counts(self) -> dict[str, int]:
        with self._connect() as connection:
            def _count(table: str, where: str = "") -> int:
                sql = f"SELECT COUNT(*) FROM {table} {where}".strip()
                return int(connection.execute(sql).fetchone()[0])

            now = _utc_now()
            return {
                "scores": _count("lead_scores"),
                "tasks": _count("follow_up_tasks"),
                "pending_tasks": _count("follow_up_tasks", "WHERE status = 'SCHEDULED'"),
                "upcoming_tasks": _count(
                    "follow_up_tasks",
                    f"WHERE status IN ('SCHEDULED', 'IN_PROGRESS') AND scheduled_for >= '{now}'",
                ),
                "overdue_tasks": _count(
                    "follow_up_tasks",
                    f"WHERE status IN ('SCHEDULED', 'IN_PROGRESS') AND scheduled_for < '{now}'",
                ),
                "completed_tasks": _count("follow_up_tasks", "WHERE status = 'COMPLETED'"),
                "reminders": _count("reminders"),
                "pending_reminders": _count("reminders", "WHERE status = 'PENDING'"),
                "rules": _count("workflow_rules"),
                "active_rules": _count("workflow_rules", "WHERE is_active = 1"),
                "executions": _count("workflow_executions"),
                "pending_approvals": _count("approval_requests", "WHERE status = 'PENDING'"),
                "pending_jobs": _count("automation_jobs", "WHERE status = 'PENDING'"),
                "failed_jobs": _count("automation_jobs", "WHERE status = 'FAILED'"),
                "audit_logs": _count("automation_audit_logs"),
                "email_drafts_pending": _count("email_drafts", "WHERE status = 'PENDING'"),
                "email_drafts_approved": _count("email_drafts", "WHERE status = 'APPROVED'"),
                "email_drafts_sent": _count("email_drafts", "WHERE status = 'SENT'"),
                "email_drafts_failed": _count("email_drafts", "WHERE status = 'FAILED'"),
            }


# Default singleton instance pointing to settings
automation_store = AutomationStore(settings.AUTOMATION_DB_FILE)
