import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from app.core.config import settings
from app.models.automation import (
    ApprovalAction,
    DEFAULT_TIMEZONE,
    to_kolkata_iso,
    to_utc_iso,
    utc_now_iso,
)
from app.services.automation_store import (
    AutomationError,
    AutomationStore,
    DuplicateIdempotencyKeyError,
    EntityNotFoundError,
    automation_store,
)
from app.services.gmail_intelligence_store import (
    GmailIntelligenceStore,
    gmail_intelligence_store,
)
from app.services.lead_scoring_service import (
    ALGORITHM_VERSION,
    DeterministicLeadScorer,
)
from app.services.sheets_service import list_leads_for_matching

logger = logging.getLogger("leadflow")


class InvalidLeadIdError(AutomationError):
    """Raised when a lead ID does not exist in CRM or intelligence data."""
    pass


class InvalidStateError(AutomationError):
    """Raised when an action is performed on an entity in an invalid state."""
    pass


class AutomationService:
    def __init__(
        self,
        store: AutomationStore | None = None,
        leads_loader: Callable[[], list[dict]] | None = None,
        intelligence_store: GmailIntelligenceStore | None = None,
    ):
        self.store = store or automation_store
        self.leads_loader = leads_loader or list_leads_for_matching
        self.intelligence_store = (
            intelligence_store or gmail_intelligence_store
        )
        self._job_handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any] | None]] = {
            "PROCESS_REMINDER": self._handle_process_reminder,
            "PROCESS_FOLLOW_UP": self._handle_process_follow_up,
            "EVALUATE_WORKFLOW": self._handle_evaluate_workflow,
            "PROCESS_APPROVAL_EXPIRY": self._handle_process_approval_expiry,
            "RECALCULATE_LEAD_SCORE": self._handle_recalculate_lead_score,
            "RETRY_GROQ_PERSONALIZATION": self._handle_retry_groq_personalization,
            "RETRY_SHEETS_SYNC": self._handle_retry_sheets_sync,
        }

    # --- Lead Validation ---
    def validate_lead_exists(self, lead_id: str) -> bool:
        """
        Validate that lead_id exists in either:
        1. Google Sheets CRM (via leads_loader)
        2. SQLite Gmail Intelligence records
        """
        if not lead_id or not str(lead_id).strip():
            return False

        normalized_id = str(lead_id).strip()

        # 1. Check CRM leads
        try:
            leads = self.leads_loader()
            if any(str(item.get("lead_id", "")).strip() == normalized_id for item in leads):
                return True
        except Exception:
            logger.warning(
                "CRM lead loading failed during lead validation for '%s'",
                normalized_id,
                exc_info=True,
            )

        # 2. Check local Intelligence database
        try:
            with self.intelligence_store._connect() as connection:
                row = connection.execute(
                    "SELECT 1 FROM gmail_message_intelligence WHERE lead_id = ? LIMIT 1",
                    (normalized_id,),
                ).fetchone()
                if row is not None:
                    return True
        except Exception:
            logger.warning(
                "Intelligence store lookup failed during lead validation for '%s'",
                normalized_id,
                exc_info=True,
            )

        return False

    def require_valid_lead(self, lead_id: str) -> None:
        if not self.validate_lead_exists(lead_id):
            raise InvalidLeadIdError(f"Lead ID '{lead_id}' not found in CRM or intelligence data")

    def _get_crm_lead(self, lead_id: str) -> dict[str, Any] | None:
        try:
            leads = self.leads_loader()
            return next(
                (item for item in leads if str(item.get("lead_id", "")).strip() == lead_id.strip()),
                None,
            )
        except Exception:
            logger.warning("Could not load CRM lead details for %s", lead_id, exc_info=True)
            return None

    # --- 1. Deterministic Lead Scoring ---
    def calculate_and_save_score(
        self,
        lead_id: str,
        actor: str = "system",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Deterministically calculate lead score from CRM, intelligence, and task signals.
        If score or tier changes, emits SCORE_UPDATED event.
        """
        self.require_valid_lead(lead_id)

        crm_lead = self._get_crm_lead(lead_id)

        # Fetch intelligence records for this lead
        intelligence_records = []
        try:
            with self.intelligence_store._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT message_id, lead_id, match_status, classification_status,
                           intent_category, sentiment, confidence, summary,
                           extracted_information, action_items, suggested_next_step,
                           received_timestamp, created_at
                    FROM gmail_message_intelligence
                    WHERE lead_id = ?
                    ORDER BY received_timestamp DESC
                    """,
                    (lead_id,),
                ).fetchall()
                intelligence_records = [dict(r) for r in rows]
        except Exception:
            logger.warning("Failed to fetch intelligence records for scoring %s", lead_id, exc_info=True)

        # Fetch tasks for urgency evaluation
        tasks = self.store.list_follow_up_tasks(lead_id=lead_id, limit=50)

        # Compute deterministic score
        scoring_result = DeterministicLeadScorer.calculate_score(
            lead_id=lead_id,
            crm_lead=crm_lead,
            intelligence_records=intelligence_records,
            tasks=tasks,
        )

        # Check existing latest score to detect change
        prev_score = self.store.get_latest_lead_score(lead_id)
        score_changed = (
            prev_score is None
            or prev_score.get("score") != scoring_result["score"]
            or prev_score.get("tier") != scoring_result["tier"]
        )

        saved = self.store.create_lead_score(
            lead_id=lead_id,
            score=scoring_result["score"],
            tier=scoring_result["tier"],
            factors=scoring_result["factors"],
            version=scoring_result["version"],
            idempotency_key=idempotency_key,
        )

        self.store.record_audit_log(
            entity_type="LEAD_SCORE",
            entity_id=saved["id"],
            action="CREATED" if prev_score is None else "RECALCULATED",
            lead_id=lead_id,
            actor=actor,
            details={
                "score": saved["score"],
                "tier": saved["tier"],
                "version": saved["version"],
                "score_changed": score_changed,
            },
        )

        # If score or tier changed, emit SCORE_UPDATED event
        if score_changed:
            try:
                self.emit_event(
                    trigger_type="SCORE_UPDATED",
                    lead_id=lead_id,
                    context_data={
                        "score": saved["score"],
                        "tier": saved["tier"],
                        "prev_score": prev_score.get("score") if prev_score else None,
                        "prev_tier": prev_score.get("tier") if prev_score else None,
                        "complaint_attention_flag": scoring_result["complaint_attention_flag"],
                    },
                    idempotency_key=f"event_score_updated_{saved['id']}",
                    actor=actor,
                )
            except Exception:
                logger.exception("Failed to emit SCORE_UPDATED event for %s", lead_id)

        return saved

    def record_lead_score(
        self,
        lead_id: str,
        score: int,
        tier: str,
        factors: dict[str, Any] | None = None,
        version: str = ALGORITHM_VERSION,
        idempotency_key: str | None = None,
        actor: str = "system",
    ) -> dict:
        """Manually record a validated lead score."""
        self.require_valid_lead(lead_id)

        result = self.store.create_lead_score(
            lead_id=lead_id,
            score=score,
            tier=tier,
            factors=factors,
            version=version,
            idempotency_key=idempotency_key,
        )

        self.store.record_audit_log(
            entity_type="LEAD_SCORE",
            entity_id=result["id"],
            action="CREATED",
            lead_id=lead_id,
            actor=actor,
            details={"score": score, "tier": tier, "version": version},
        )
        return result

    def get_latest_lead_score(self, lead_id: str) -> dict:
        self.require_valid_lead(lead_id)
        score = self.store.get_latest_lead_score(lead_id)
        if not score:
            # If no score exists yet, calculate deterministically on the fly
            score = self.calculate_and_save_score(lead_id, actor="system")
        return score

    def list_lead_score_history(self, lead_id: str) -> list[dict]:
        self.require_valid_lead(lead_id)
        return self.store.list_lead_score_history(lead_id)

    def recalculate_all_scores(self, actor: str = "system") -> dict[str, Any]:
        """Recalculate scores for all known leads."""
        recalculated_leads = []
        results = []
        try:
            crm_leads = self.leads_loader()
            for lead in crm_leads:
                lid = lead.get("lead_id")
                if lid:
                    try:
                        res = self.calculate_and_save_score(lid, actor=actor)
                        recalculated_leads.append(lid)
                        results.append(res)
                    except Exception:
                        logger.warning("Failed recalculating score for lead %s", lid, exc_info=True)
        except Exception:
            logger.exception("Failed loading leads for score recalculation")

        return {
            "recalculated": len(recalculated_leads),
            "lead_ids": recalculated_leads,
            "results": results,
        }

    def get_lead_leaderboard(
        self,
        limit: int = 50,
        tier: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return ranked leaderboard of leads with CRM context."""
        scores = self.store.get_lead_leaderboard(limit=limit, tier=tier)
        leaderboard = []

        # Index CRM details for fast enrichment
        crm_index: dict[str, dict] = {}
        try:
            leads = self.leads_loader()
            for l in leads:
                lid = str(l.get("lead_id", "")).strip()
                if lid:
                    crm_index[lid] = l
        except Exception:
            logger.warning("Could not load CRM leads for leaderboard enrichment", exc_info=True)

        for s in scores:
            lid = s["lead_id"]
            crm_item = crm_index.get(lid, {})
            factors = s.get("factors") or {}
            complaint_flag = factors.get("complaint_attention_flag", False)

            # Compact factor scores
            factors_summary = {
                k: v.get("score", 0)
                for k, v in factors.items()
                if isinstance(v, dict) and "score" in v
            }

            leaderboard.append({
                "lead_id": lid,
                "name": crm_item.get("name", ""),
                "email": crm_item.get("email", ""),
                "company": crm_item.get("company", ""),
                "score": s["score"],
                "tier": s["tier"],
                "complaint_attention_flag": complaint_flag,
                "factors_summary": factors_summary,
                "calculated_at": s["created_at"],
            })

        return leaderboard

    # --- 2. Follow-Up Tasks ---
    def create_follow_up_task(
        self,
        lead_id: str,
        title: str,
        scheduled_for: str,
        description: str = "",
        timezone_str: str = DEFAULT_TIMEZONE,
        priority: str = "MEDIUM",
        channel: str = "EMAIL",
        generate_reminder: bool = False,
        reminder_minutes_before: int = 15,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        actor: str = "system",
    ) -> dict:
        self.require_valid_lead(lead_id)
        # Interpret timezone-naive input using the supplied valid timezone
        utc_scheduled_for = to_utc_iso(scheduled_for, tz_name=timezone_str)

        task = self.store.create_follow_up_task(
            lead_id=lead_id,
            title=title,
            scheduled_for=utc_scheduled_for,
            description=description,
            timezone_str=timezone_str,
            priority=priority,
            channel=channel,
            metadata=metadata,
            idempotency_key=idempotency_key,
        )

        # Enqueue persistent background job to process the follow up when due
        job_idempotency_key = f"job_task_{task['id']}"
        self.store.enqueue_job(
            job_type="PROCESS_FOLLOW_UP",
            payload={"task_id": task["id"], "lead_id": lead_id},
            scheduled_at=utc_scheduled_for,
            idempotency_key=job_idempotency_key,
        )

        # Optionally generate an associated reminder
        if generate_reminder:
            try:
                task_dt = datetime.fromisoformat(utc_scheduled_for.replace("Z", "+00:00"))
                remind_dt = task_dt - timedelta(minutes=max(0, reminder_minutes_before))
                rem_utc = remind_dt.astimezone(timezone.utc).isoformat()

                rem_key = f"rem_task_{task['id']}"
                self.create_reminder(
                    lead_id=lead_id,
                    task_id=task["id"],
                    title=f"Reminder: {title}",
                    remind_at=rem_utc,
                    timezone_str=timezone_str,
                    channel="INTERNAL_LOG",
                    idempotency_key=rem_key,
                    actor=actor,
                )
            except Exception:
                logger.exception("Failed auto-generating reminder for task %s", task["id"])

        self.store.record_audit_log(
            entity_type="FOLLOW_UP_TASK",
            entity_id=task["id"],
            action="CREATED",
            lead_id=lead_id,
            actor=actor,
            details={
                "title": title,
                "scheduled_for": utc_scheduled_for,
                "priority": priority,
                "channel": channel,
                "generate_reminder": generate_reminder,
            },
        )
        return task

    def get_follow_up_task(self, task_id: str) -> dict:
        task = self.store.get_follow_up_task(task_id)
        if not task:
            raise EntityNotFoundError(f"Follow-up task '{task_id}' not found")
        return task

    def update_follow_up_task(
        self,
        task_id: str,
        status: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        scheduled_for: str | None = None,
        timezone_str: str | None = None,
        metadata: dict[str, Any] | None = None,
        actor: str = "system",
    ) -> dict:
        existing = self.get_follow_up_task(task_id)
        tz = timezone_str or existing.get("timezone") or DEFAULT_TIMEZONE
        utc_scheduled_for = to_utc_iso(scheduled_for, tz_name=tz) if scheduled_for else None

        updated = self.store.update_follow_up_task(
            task_id=task_id,
            status=status,
            description=description,
            priority=priority,
            scheduled_for=utc_scheduled_for,
            timezone_str=timezone_str,
            metadata=metadata,
        )

        self.store.record_audit_log(
            entity_type="FOLLOW_UP_TASK",
            entity_id=task_id,
            action="UPDATED",
            lead_id=existing["lead_id"],
            actor=actor,
            details={
                "status": status,
                "priority": priority,
                "scheduled_for": utc_scheduled_for,
            },
        )
        return updated  # type: ignore

    def reschedule_task(
        self,
        task_id: str,
        new_scheduled_for: str,
        timezone_str: str = DEFAULT_TIMEZONE,
        actor: str = "system",
    ) -> dict:
        existing = self.get_follow_up_task(task_id)
        utc_new_time = to_utc_iso(new_scheduled_for, tz_name=timezone_str)

        updated = self.store.reschedule_task(
            task_id=task_id,
            new_scheduled_for=utc_new_time,
            timezone_str=timezone_str,
        )

        # Reschedule follow up job
        job_key = f"job_task_{task_id}_resched_{uuid_hex_prefix()}"
        self.store.enqueue_job(
            job_type="PROCESS_FOLLOW_UP",
            payload={"task_id": task_id, "lead_id": existing["lead_id"]},
            scheduled_at=utc_new_time,
            idempotency_key=job_key,
        )

        self.store.record_audit_log(
            entity_type="FOLLOW_UP_TASK",
            entity_id=task_id,
            action="RESCHEDULED",
            lead_id=existing["lead_id"],
            actor=actor,
            details={"previous_time": existing["scheduled_for"], "new_time": utc_new_time},
        )
        return updated  # type: ignore

    def complete_task(self, task_id: str, actor: str = "system") -> dict:
        existing = self.get_follow_up_task(task_id)
        updated = self.store.complete_task(task_id)
        self.store.record_audit_log(
            entity_type="FOLLOW_UP_TASK",
            entity_id=task_id,
            action="COMPLETED",
            lead_id=existing["lead_id"],
            actor=actor,
            details={"status": "COMPLETED"},
        )
        return updated  # type: ignore

    def cancel_task(self, task_id: str, actor: str = "system") -> dict:
        existing = self.get_follow_up_task(task_id)
        updated = self.store.cancel_task(task_id)
        self.store.record_audit_log(
            entity_type="FOLLOW_UP_TASK",
            entity_id=task_id,
            action="CANCELLED",
            lead_id=existing["lead_id"],
            actor=actor,
            details={"status": "CANCELLED"},
        )
        return updated  # type: ignore

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
        if lead_id:
            self.require_valid_lead(lead_id)
        return self.store.list_follow_up_tasks(
            lead_id=lead_id,
            status=status,
            priority=priority,
            channel=channel,
            upcoming_only=upcoming_only,
            overdue_only=overdue_only,
            limit=limit,
            offset=offset,
        )

    def list_upcoming_tasks(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self.store.list_upcoming_tasks(limit=limit, offset=offset)

    def list_overdue_tasks(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self.store.list_overdue_tasks(limit=limit, offset=offset)

    # --- 3. Reminders ---
    def create_reminder(
        self,
        lead_id: str,
        title: str,
        remind_at: str,
        task_id: str | None = None,
        timezone_str: str = DEFAULT_TIMEZONE,
        recipient: str = "",
        channel: str = "INTERNAL_LOG",
        idempotency_key: str | None = None,
        actor: str = "system",
    ) -> dict:
        self.require_valid_lead(lead_id)
        if task_id:
            self.get_follow_up_task(task_id)

        utc_remind_at = to_utc_iso(remind_at, tz_name=timezone_str)

        reminder = self.store.create_reminder(
            lead_id=lead_id,
            title=title,
            remind_at=utc_remind_at,
            task_id=task_id,
            timezone_str=timezone_str,
            recipient=recipient,
            channel=channel,
            idempotency_key=idempotency_key,
        )

        job_idempotency_key = f"job_rem_{reminder['id']}"
        self.store.enqueue_job(
            job_type="PROCESS_REMINDER",
            payload={"reminder_id": reminder["id"], "lead_id": lead_id},
            scheduled_at=utc_remind_at,
            idempotency_key=job_idempotency_key,
        )

        self.store.record_audit_log(
            entity_type="REMINDER",
            entity_id=reminder["id"],
            action="CREATED",
            lead_id=lead_id,
            actor=actor,
            details={
                "title": title,
                "remind_at": utc_remind_at,
                "task_id": task_id,
                "channel": channel,
            },
        )
        return reminder

    def get_reminder(self, reminder_id: str) -> dict:
        reminder = self.store.get_reminder(reminder_id)
        if not reminder:
            raise EntityNotFoundError(f"Reminder '{reminder_id}' not found")
        return reminder

    def dismiss_reminder(self, reminder_id: str, actor: str = "system") -> dict:
        existing = self.get_reminder(reminder_id)
        if existing["status"] == "DISMISSED":
            return existing

        updated = self.store.dismiss_reminder(reminder_id)
        self.store.record_audit_log(
            entity_type="REMINDER",
            entity_id=reminder_id,
            action="DISMISSED",
            lead_id=existing["lead_id"],
            actor=actor,
            details={"status": "DISMISSED"},
        )
        return updated  # type: ignore

    def list_reminders(
        self,
        lead_id: str | None = None,
        task_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        if lead_id:
            self.require_valid_lead(lead_id)
        return self.store.list_reminders(
            lead_id=lead_id,
            task_id=task_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    def list_pending_reminders(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self.store.list_pending_reminders(limit=limit, offset=offset)

    def list_completed_reminders(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self.store.list_completed_reminders(limit=limit, offset=offset)

    # --- 4. Workflow Rules & Executions ---
    def create_workflow_rule(
        self,
        name: str,
        trigger_type: str,
        conditions: dict[str, Any] | None = None,
        actions: list[dict[str, Any]] | None = None,
        requires_approval: bool = True,
        is_active: bool = True,
        actor: str = "system",
    ) -> dict:
        rule = self.store.create_workflow_rule(
            name=name,
            trigger_type=trigger_type,
            conditions=conditions,
            actions=actions,
            requires_approval=requires_approval,
            is_active=is_active,
        )
        self.store.record_audit_log(
            entity_type="WORKFLOW_RULE",
            entity_id=rule["id"],
            action="CREATED",
            actor=actor,
            details={
                "name": name,
                "trigger_type": trigger_type,
                "requires_approval": requires_approval,
            },
        )
        return rule

    def get_workflow_rule(self, rule_id: str) -> dict:
        rule = self.store.get_workflow_rule(rule_id)
        if not rule:
            raise EntityNotFoundError(f"Workflow rule '{rule_id}' not found")
        return rule

    def update_workflow_rule(
        self,
        rule_id: str,
        name: str | None = None,
        conditions: dict[str, Any] | None = None,
        actions: list[dict[str, Any]] | None = None,
        requires_approval: bool | None = None,
        is_active: bool | None = None,
        actor: str = "system",
    ) -> dict:
        existing = self.get_workflow_rule(rule_id)
        updated = self.store.update_workflow_rule(
            rule_id=rule_id,
            name=name,
            conditions=conditions,
            actions=actions,
            requires_approval=requires_approval,
            is_active=is_active,
        )
        self.store.record_audit_log(
            entity_type="WORKFLOW_RULE",
            entity_id=rule_id,
            action="UPDATED",
            actor=actor,
            details={"name": name, "is_active": is_active, "requires_approval": requires_approval},
        )
        return updated  # type: ignore

    def delete_workflow_rule(self, rule_id: str, actor: str = "system") -> bool:
        self.get_workflow_rule(rule_id)
        success = self.store.delete_workflow_rule(rule_id)
        if success:
            self.store.record_audit_log(
                entity_type="WORKFLOW_RULE",
                entity_id=rule_id,
                action="DELETED",
                actor=actor,
            )
        return success

    def list_workflow_rules(
        self,
        trigger_type: str | None = None,
        is_active: bool | None = None,
    ) -> list[dict]:
        return self.store.list_workflow_rules(
            trigger_type=trigger_type, is_active=is_active
        )

    # --- Conditional Engine Evaluator ---
    def evaluate_rule_conditions(
        self,
        rule: dict[str, Any],
        lead_id: str,
        context_data: dict[str, Any],
    ) -> bool:
        """
        Evaluate rule conditions against lead score, CRM, and event context.
        """
        conditions = rule.get("conditions") or {}
        if not conditions:
            return True

        # Fetch lead's latest score
        latest_score = self.store.get_latest_lead_score(lead_id)
        score_val = latest_score.get("score", 0) if latest_score else 0
        tier_val = latest_score.get("tier", "COLD") if latest_score else "COLD"
        factors = latest_score.get("factors", {}) if latest_score else {}

        # 1. min_score
        if "min_score" in conditions:
            if score_val < conditions["min_score"]:
                return False

        # 2. max_score
        if "max_score" in conditions:
            if score_val > conditions["max_score"]:
                return False

        # 3. tier
        if "tier" in conditions:
            expected_tier = conditions["tier"]
            if isinstance(expected_tier, list):
                if tier_val not in expected_tier:
                    return False
            elif tier_val != expected_tier:
                return False

        # 4. intent_category
        if "intent_category" in conditions:
            intent_val = (
                context_data.get("intent_category")
                or factors.get("customer_intent", {}).get("category")
            )
            expected_intent = conditions["intent_category"]
            if isinstance(expected_intent, list):
                if intent_val not in expected_intent:
                    return False
            elif intent_val != expected_intent:
                return False

        # 5. sentiment
        if "sentiment" in conditions:
            sentiment_val = (
                context_data.get("sentiment")
                or factors.get("sentiment", {}).get("sentiment")
            )
            expected_sentiment = conditions["sentiment"]
            if isinstance(expected_sentiment, list):
                if sentiment_val not in expected_sentiment:
                    return False
            elif sentiment_val != expected_sentiment:
                return False

        # 6. complaint_attention_flag
        if "complaint_attention_flag" in conditions:
            flag = factors.get("complaint_attention_flag", False)
            if flag != conditions["complaint_attention_flag"]:
                return False

        # 7. has_upcoming_follow_up
        if "has_upcoming_follow_up" in conditions:
            upcoming = self.store.list_upcoming_tasks(limit=10)
            lead_upcoming = any(t["lead_id"] == lead_id for t in upcoming)
            if lead_upcoming != conditions["has_upcoming_follow_up"]:
                return False

        # 8. has_no_follow_up
        if "has_no_follow_up" in conditions:
            open_tasks = self.store.list_follow_up_tasks(lead_id=lead_id, status="SCHEDULED", limit=1)
            has_none = len(open_tasks) == 0
            if has_none != conditions["has_no_follow_up"]:
                return False

        # 9. CRM attributes check
        crm_lead = self._get_crm_lead(lead_id) or {}
        if "crm_service" in conditions:
            if str(crm_lead.get("service") or "").lower() != str(conditions["crm_service"]).lower():
                return False
        if "crm_has_budget" in conditions:
            b = str(crm_lead.get("budget") or "").strip().lower()
            has_b = bool(b and b not in ("none", "0", "$0", "n/a"))
            if has_b != conditions["crm_has_budget"]:
                return False

        return True

    def trigger_workflow_execution(
        self,
        rule_id: str,
        lead_id: str,
        trigger_event: str,
        context_data: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        actor: str = "system",
    ) -> dict:
        """
        Execute or queue a workflow rule for a lead.
        Enforces human approval safeguards.
        """
        self.require_valid_lead(lead_id)
        rule = self.get_workflow_rule(rule_id)

        sensitive_actions = {"SEND_EMAIL", "UPDATE_CRM", "EXTERNAL_WEBHOOK"}
        rule_actions = rule.get("actions", [])
        has_sensitive_action = any(
            isinstance(act, dict) and act.get("type") in sensitive_actions
            for act in rule_actions
        )
        needs_approval = rule.get("requires_approval", True) or has_sensitive_action

        initial_status = "AWAITING_APPROVAL" if needs_approval else "RUNNING"

        execution = self.store.create_workflow_execution(
            rule_id=rule_id,
            lead_id=lead_id,
            trigger_event=trigger_event,
            status=initial_status,
            context_data=context_data,
            idempotency_key=idempotency_key,
        )

        self.store.record_audit_log(
            entity_type="WORKFLOW_EXECUTION",
            entity_id=execution["id"],
            action="EXECUTION_STARTED",
            lead_id=lead_id,
            actor=actor,
            details={
                "rule_id": rule_id,
                "trigger_event": trigger_event,
                "status": initial_status,
            },
        )

        if needs_approval:
            appr_key = f"appr_exec_{execution['id']}"
            appr = self.store.create_approval_request(
                lead_id=lead_id,
                action_type=(
                    rule_actions[0].get("type", "EXECUTE_WORKFLOW")
                    if rule_actions
                    else "EXECUTE_WORKFLOW"
                ),
                action_payload={
                    "rule_id": rule_id,
                    "rule_name": rule["name"],
                    "actions": rule_actions,
                    "context": context_data or {},
                },
                workflow_execution_id=execution["id"],
                requested_by=actor,
                idempotency_key=appr_key,
            )
            self.store.record_audit_log(
                entity_type="APPROVAL_REQUEST",
                entity_id=appr["id"],
                action="CREATED",
                lead_id=lead_id,
                actor="system",
                details={"execution_id": execution["id"], "action_type": appr["action_type"]},
            )
        else:
            # Execute non-sensitive actions immediately
            executed_results = []
            try:
                for action in rule_actions:
                    act_type = action.get("type")
                    params = action.get("params", {})
                    if act_type == "CREATE_FOLLOW_UP":
                        delay_hours = int(params.get("delay_hours", 24))
                        target_time = (datetime.now(timezone.utc) + timedelta(hours=delay_hours)).isoformat()
                        t = self.create_follow_up_task(
                            lead_id=lead_id,
                            title=params.get("title", "Automated Follow-up"),
                            scheduled_for=target_time,
                            priority=params.get("priority", "MEDIUM"),
                            channel=params.get("channel", "MANUAL"),
                            actor="workflow_engine",
                        )
                        executed_results.append({"type": act_type, "task_id": t["id"]})
                    elif act_type == "CREATE_REMINDER":
                        delay_hours = int(params.get("delay_hours", 2))
                        target_time = (datetime.now(timezone.utc) + timedelta(hours=delay_hours)).isoformat()
                        r = self.create_reminder(
                            lead_id=lead_id,
                            title=params.get("title", "Automated Reminder"),
                            remind_at=target_time,
                            channel="INTERNAL_LOG",
                            actor="workflow_engine",
                        )
                        executed_results.append({"type": act_type, "reminder_id": r["id"]})
                    elif act_type == "UPDATE_LEAD_PRIORITY":
                        executed_results.append({"type": act_type, "priority": params.get("priority", "HIGH")})
                    elif act_type == "CREATE_INTERNAL_NOTIFICATION":
                        self.store.record_audit_log(
                            entity_type="WORKFLOW_EXECUTION",
                            entity_id=execution["id"],
                            action="NOTIFICATION",
                            lead_id=lead_id,
                            actor="workflow_engine",
                            details={"message": params.get("message", "Workflow notification")},
                        )
                        executed_results.append({"type": act_type, "status": "notified"})

                execution = self.store.update_workflow_execution(
                    execution_id=execution["id"],
                    status="COMPLETED",
                    result_data={"executed_actions": executed_results},
                    completed=True,
                )
            except Exception as exc:
                logger.exception("Failed executing actions for workflow execution %s", execution["id"])
                execution = self.store.update_workflow_execution(
                    execution_id=execution["id"],
                    status="FAILED",
                    error_message=str(exc),
                    result_data={"executed_actions": executed_results},
                    completed=True,
                )
                self.store.record_audit_log(
                    entity_type="WORKFLOW_EXECUTION",
                    entity_id=execution["id"],
                    action="EXECUTION_FAILED",
                    lead_id=lead_id,
                    actor=actor,
                    details={"error": str(exc)},
                )
                raise

        return execution

    def emit_event(
        self,
        trigger_type: str,
        lead_id: str,
        context_data: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        actor: str = "system",
    ) -> list[dict[str, Any]]:
        """
        Emit an event into the automation engine (LEAD_CREATED, INTENT_CLASSIFIED, SCORE_UPDATED, etc.)
        Finds all active rules matching trigger_type, evaluates conditions, and triggers execution.
        """
        self.require_valid_lead(lead_id)
        ctx = context_data or {}
        active_rules = self.store.list_active_rules_for_trigger(trigger_type)
        executions = []

        # If INTENT_CLASSIFIED, automatically recalculate lead score deterministically!
        if trigger_type == "INTENT_CLASSIFIED":
            try:
                score_key = f"score_recalc_{ctx.get('message_id') or lead_id}_{uuid_hex_prefix()}"
                self.calculate_and_save_score(lead_id, actor="intelligence_service", idempotency_key=score_key)
            except Exception:
                logger.warning("Score recalculation failed during INTENT_CLASSIFIED event for %s", lead_id, exc_info=True)

        for rule in active_rules:
            try:
                if self.evaluate_rule_conditions(rule, lead_id, ctx):
                    rule_idem_key = (
                        f"{idempotency_key}_{rule['id']}" if idempotency_key else None
                    )
                    exec_res = self.trigger_workflow_execution(
                        rule_id=rule["id"],
                        lead_id=lead_id,
                        trigger_event=trigger_type,
                        context_data=ctx,
                        idempotency_key=rule_idem_key,
                        actor=actor,
                    )
                    executions.append(exec_res)
            except DuplicateIdempotencyKeyError:
                logger.info(
                    "Workflow rule %s already executed for event %s (idempotency key match)",
                    rule["id"],
                    trigger_type,
                )
            except Exception:
                logger.exception("Error evaluating workflow rule %s for lead %s", rule["id"], lead_id)

        return executions

    def get_workflow_execution(self, execution_id: str) -> dict:
        execution = self.store.get_workflow_execution(execution_id)
        if not execution:
            raise EntityNotFoundError(f"Workflow execution '{execution_id}' not found")
        return execution

    def list_workflow_executions(
        self,
        lead_id: str | None = None,
        rule_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        if lead_id:
            self.require_valid_lead(lead_id)
        return self.store.list_workflow_executions(
            lead_id=lead_id,
            rule_id=rule_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    # --- 5. Approvals (Human-in-the-Loop Safeguard) ---
    def record_approval_decision(
        self,
        approval_id: str,
        action: ApprovalAction,
        reviewed_by: str,
        rejection_reason: str | None = None,
        decision_notes: str | None = None,
    ) -> dict:
        approval = self.store.get_approval_request(approval_id)
        if not approval:
            raise EntityNotFoundError(f"Approval request '{approval_id}' not found")

        if approval["status"] != "PENDING":
            raise InvalidStateError(
                f"Approval request '{approval_id}' has already been reviewed (current status: {approval['status']})"
            )

        updated = self.store.record_approval_decision(
            approval_id=approval_id,
            action=action,
            reviewed_by=reviewed_by,
            rejection_reason=rejection_reason,
        )

        # Update linked workflow execution with explicit authorization vs execution status
        if approval["workflow_execution_id"]:
            new_exec_status = "COMPLETED" if action == "APPROVE" else "FAILED"
            result_payload = {
                "approval_id": approval_id,
                "action_type": approval["action_type"],
                "decision": action,
                "reviewed_by": reviewed_by,
                "authorization_granted": action == "APPROVE",
                "action_executed": False,  # Safety guarantee: Approval grants authorization; customer emails/sensitive actions require manual execution
            }
            self.store.update_workflow_execution(
                execution_id=approval["workflow_execution_id"],
                status=new_exec_status,
                result_data=result_payload,
                error_message=rejection_reason if action == "REJECT" else None,
                completed=True,
            )

        # Synchronize linked Email Draft and CRM status when approving an email action
        if approval.get("action_type") == "SEND_EMAIL":
            try:
                draft = self.store.get_email_draft_by_approval_id(approval_id)
                if not draft and isinstance(approval.get("action_payload"), dict):
                    draft_id = approval["action_payload"].get("draft_id")
                    if draft_id:
                        draft = self.store.get_email_draft(draft_id)

                if draft:
                    if action == "APPROVE":
                        self.store.record_email_draft_approved(draft["id"], approved_by=reviewed_by)
                        try:
                            from app.services.sheets_service import update_lead_email_status
                            update_lead_email_status(draft["lead_id"], email_status="APPROVED")
                        except Exception:
                            logger.warning("Could not update sheets email_status to APPROVED for %s", draft["lead_id"], exc_info=True)
                    elif action == "REJECT":
                        self.store.update_email_draft(
                            draft["id"],
                            status="REJECTED",
                            error_message=f"Rejected: {rejection_reason or 'No reason provided'}",
                        )
                        try:
                            from app.services.sheets_service import update_lead_email_status
                            update_lead_email_status(
                                draft["lead_id"],
                                email_status="FAILED",
                                error_message=f"Rejected: {rejection_reason or 'No reason provided'}",
                            )
                        except Exception:
                            logger.warning("Could not update sheets email_status to FAILED for %s", draft["lead_id"], exc_info=True)
            except Exception:
                logger.warning("Could not sync email draft status for approval %s", approval_id, exc_info=True)

        self.store.record_audit_log(
            entity_type="APPROVAL_REQUEST",
            entity_id=approval_id,
            action=action,
            lead_id=approval["lead_id"],
            actor=reviewed_by,
            details={
                "action": action,
                "rejection_reason": rejection_reason,
                "decision_notes": decision_notes,
                "workflow_execution_id": approval["workflow_execution_id"],
            },
        )
        return updated  # type: ignore

    def expire_stale_approvals(self, max_age_hours: int = 72) -> list[dict]:
        expired = self.store.expire_stale_approvals(max_age_hours=max_age_hours)
        for appr in expired:
            # Terminate linked workflow execution as expired/failed
            if appr.get("workflow_execution_id"):
                self.store.update_workflow_execution(
                    execution_id=appr["workflow_execution_id"],
                    status="FAILED",
                    result_data={
                        "approval_id": appr["id"],
                        "authorization_granted": False,
                        "action_executed": False,
                        "reason": "expired",
                    },
                    error_message=f"Approval request expired after {max_age_hours} hours without review",
                    completed=True,
                )
            self.store.record_audit_log(
                entity_type="APPROVAL_REQUEST",
                entity_id=appr["id"],
                action="EXPIRED",
                lead_id=appr["lead_id"],
                actor="system",
                details={"reason": f"Approval request expired after {max_age_hours} hours"},
            )
        return expired

    def get_approval_request(self, approval_id: str) -> dict:
        approval = self.store.get_approval_request(approval_id)
        if not approval:
            raise EntityNotFoundError(f"Approval request '{approval_id}' not found")
        return approval

    def list_approval_requests(
        self,
        status: str | None = None,
        lead_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        if lead_id:
            self.require_valid_lead(lead_id)
        return self.store.list_approval_requests(
            status=status, lead_id=lead_id, limit=limit, offset=offset
        )

    # --- 6. Audit Logs ---
    def list_audit_logs(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        lead_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        return self.store.list_audit_logs(
            entity_type=entity_type,
            entity_id=entity_id,
            lead_id=lead_id,
            limit=limit,
            offset=offset,
        )

    # --- 7. Persistent Job Handlers ---
    def _handle_process_reminder(self, payload: dict[str, Any]) -> dict[str, Any]:
        reminder_id = payload.get("reminder_id")
        if not reminder_id:
            raise ValueError("Payload missing 'reminder_id'")

        reminder = self.store.get_reminder(reminder_id)
        if not reminder:
            return {"status": "skipped", "reason": "reminder_not_found"}

        if reminder["status"] == "PENDING":
            self.store.update_reminder_status(reminder_id, "SENT")
            self.store.record_audit_log(
                entity_type="REMINDER",
                entity_id=reminder_id,
                action="REMINDER_TRIGGERED",
                lead_id=reminder["lead_id"],
                details={"title": reminder["title"], "channel": reminder["channel"]},
            )
            return {"status": "sent", "reminder_id": reminder_id}
        return {"status": "already_processed", "reminder_id": reminder_id}

    def _handle_process_follow_up(self, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = payload.get("task_id")
        if not task_id:
            raise ValueError("Payload missing 'task_id'")

        task = self.store.get_follow_up_task(task_id)
        if not task:
            return {"status": "skipped", "reason": "task_not_found"}

        if task["status"] == "SCHEDULED":
            # Safety Rule: Do NOT send customer emails automatically!
            self.store.update_follow_up_task(task_id, status="IN_PROGRESS")
            self.store.record_audit_log(
                entity_type="FOLLOW_UP_TASK",
                entity_id=task_id,
                action="TASK_DUE",
                lead_id=task["lead_id"],
                details={"title": task["title"], "channel": task["channel"]},
            )
            return {"status": "processed", "task_id": task_id}
        return {"status": "already_processed", "task_id": task_id}

    def _handle_evaluate_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        lead_id = payload.get("lead_id")
        trigger_type = payload.get("trigger_type", "SCHEDULED_TIME")
        if lead_id:
            execs = self.emit_event(trigger_type, lead_id, payload.get("context_data", {}))
            return {"status": "evaluated", "executions": len(execs)}
        return {"status": "skipped", "reason": "no_lead_id"}

    def _handle_process_approval_expiry(self, payload: dict[str, Any]) -> dict[str, Any]:
        max_age = int(payload.get("max_age_hours", 72))
        expired = self.expire_stale_approvals(max_age_hours=max_age)
        return {"status": "processed", "expired_count": len(expired)}

    def _handle_recalculate_lead_score(self, payload: dict[str, Any]) -> dict[str, Any]:
        lead_id = payload.get("lead_id")
        if not lead_id:
            raise ValueError("Payload missing 'lead_id'")
        res = self.calculate_and_save_score(lead_id)
        return {"status": "recalculated", "lead_id": lead_id, "score": res["score"]}

    def _handle_retry_groq_personalization(self, payload: dict[str, Any]) -> dict[str, Any]:
        submission_id = payload.get("submission_id")
        lead_id = payload.get("lead_id")
        normalized = payload.get("normalized_lead") or {}
        if not lead_id:
            raise ValueError("Payload missing 'lead_id'")

        from app.models.lead import LeadCreate
        from app.services.groq_service import generate_personalized_email
        from app.services.sheets_service import update_lead_ai_response

        lead_obj = LeadCreate(
            name=normalized.get("name", "Valued Customer"),
            email=normalized.get("email"),
            phone=normalized.get("phone"),
            company=normalized.get("company"),
            service=normalized.get("service", "General Inquiry"),
            requirements=normalized.get("requirements", "Inquiry details"),
            budget=normalized.get("budget"),
            preferred_contact="email",
            consent=normalized.get("consent", False),
        )

        ai_result = generate_personalized_email(lead_obj)
        update_lead_ai_response(
            lead_id=lead_id,
            ai_subject=ai_result.subject,
            ai_response=ai_result.body,
            ai_status="SUCCESS",
            lead_summary=ai_result.lead_summary,
            suggested_next_step=ai_result.suggested_next_step,
        )

        if submission_id:
            self.store.update_lead_submission(
                submission_id=submission_id,
                processing_status="COMPLETED",
                lead_id=lead_id,
            )

        return {"status": "retried", "lead_id": lead_id, "ai_status": "SUCCESS"}

    def _handle_retry_sheets_sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        submission_id = payload.get("submission_id")
        lead_id = payload.get("lead_id")
        lead_record = payload.get("lead_record") or {}
        is_existing = payload.get("is_existing", False)
        if not lead_id or not lead_record:
            raise ValueError("Payload missing 'lead_id' or 'lead_record'")

        from app.services.sheets_service import append_lead, update_lead_crm_row

        if is_existing:
            update_lead_crm_row(lead_id, lead_record)
        else:
            append_lead(lead_record)

        if submission_id:
            self.store.update_lead_submission(
                submission_id=submission_id,
                processing_status="COMPLETED",
                lead_id=lead_id,
            )

        return {"status": "synced", "lead_id": lead_id}

    def process_due_jobs(self, batch_size: int = 10) -> dict[str, int]:
        """
        Atomically claim and process due persistent jobs.
        """
        claimed = self.store.claim_due_jobs(batch_size=batch_size)
        succeeded = 0
        failed = 0

        for job in claimed:
            job_id = job["id"]
            job_type = job["job_type"]
            payload = job["payload"]

            handler = self._job_handlers.get(job_type)
            if not handler:
                logger.error("No handler registered for job type '%s'", job_type)
                self.store.fail_job(job_id, f"No handler for job type '{job_type}'", retry=False)
                failed += 1
                continue

            try:
                result = handler(payload)
                self.store.complete_job(job_id, result=result)
                self.store.record_audit_log(
                    entity_type="JOB",
                    entity_id=job_id,
                    action="JOB_COMPLETED",
                    details={"job_type": job_type, "result": result},
                )
                succeeded += 1
            except Exception as exc:
                logger.exception("Persistent automation job '%s' (%s) failed", job_id, job_type)
                self.store.fail_job(job_id, error=str(exc), retry=True)
                self.store.record_audit_log(
                    entity_type="JOB",
                    entity_id=job_id,
                    action="JOB_RETRY" if job["attempts"] < job["max_retries"] else "JOB_FAILED",
                    details={"job_type": job_type, "error": str(exc), "attempt": job["attempts"]},
                )
                failed += 1

        return {
            "processed": len(claimed),
            "succeeded": succeeded,
            "failed": failed,
        }


def uuid_hex_prefix() -> str:
    import uuid
    return uuid.uuid4().hex[:8]


# --- Background Worker Manager ---
class AutomationWorker:
    def __init__(
        self,
        service: AutomationService,
        poll_interval: int = 10,
    ):
        self.service = service
        self.poll_interval = max(1, poll_interval)
        self.is_running = False
        self._task: asyncio.Task | None = None
        self._loop_count = 0

    async def _run(self) -> None:
        logger.info(
            "Automation background worker started (poll interval: %ds)",
            self.poll_interval,
        )
        while self.is_running:
            try:
                await asyncio.to_thread(self.service.process_due_jobs)
                self._loop_count += 1
                # Periodically check and expire stale approvals (~every 6 loops)
                if self._loop_count % 6 == 0:
                    await asyncio.to_thread(self.service.expire_stale_approvals)
            except Exception:
                logger.exception("Error in automation background job worker")

            try:
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
        logger.info("Automation background worker stopped")

    def start(self) -> None:
        if not self.is_running:
            self.is_running = True
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self.is_running:
            self.is_running = False
            if self._task is not None:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
                self._task = None


# Default singletons
automation_service = AutomationService(
    store=automation_store,
    leads_loader=list_leads_for_matching,
    intelligence_store=gmail_intelligence_store,
)

automation_worker = AutomationWorker(
    service=automation_service,
    poll_interval=settings.AUTOMATION_WORKER_POLL_INTERVAL_SECONDS,
)


async def start_automation_worker() -> None:
    if settings.AUTOMATION_WORKER_ENABLED:
        automation_worker.start()


async def stop_automation_worker() -> None:
    await automation_worker.stop()
