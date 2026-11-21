from datetime import datetime, timezone
import json
import logging
from typing import Any

from app.models.automation import ScoreTier

logger = logging.getLogger("leadflow")

ALGORITHM_VERSION = "v2-deterministic"


def _parse_iso_to_utc(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    try:
        val = str(iso_str).strip()
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


class DeterministicLeadScorer:
    """
    Deterministic Lead Scoring Engine for LeadFlow AI.
    Calculates lead scores strictly via transparent Python business logic.
    Maximum total score: 100 points.

    Factors:
    1. Customer intent (max 30)
    2. Sentiment (max 20)
    3. Engagement and response activity (max 15)
    4. Budget and buying signals (max 15)
    5. Follow-up urgency (max 10)
    6. Recency of interaction (max 10)
    """

    # Intent points mapping
    INTENT_POINTS: dict[str, tuple[int, str]] = {
        "MEETING_REQUEST": (30, "Customer requested a meeting (highest conversion signal)."),
        "NEGOTIATION": (28, "Customer actively negotiating terms/pricing."),
        "INTERESTED": (25, "Customer expressed explicit interest in offerings."),
        "PRICING_INQUIRY": (22, "Customer inquired about pricing and packaging."),
        "INFORMATION_REQUEST": (15, "Customer requested additional product or service information."),
        "FOLLOW_UP": (12, "Customer follow-up discussion in progress."),
        "COMPLAINT": (10, "Customer registered a complaint; attention flag raised."),
        "OUT_OF_OFFICE": (5, "Out-of-office autoreply received; not treated as disinterest."),
        "OTHER": (5, "Uncategorized inquiry received."),
        "NOT_INTERESTED": (0, "Customer explicitly stated disinterest."),
    }

    # Sentiment points mapping
    SENTIMENT_POINTS: dict[str, tuple[int, str]] = {
        "POSITIVE": (20, "Positive customer sentiment detected."),
        "MIXED": (12, "Mixed sentiment detected across communication."),
        "NEUTRAL": (10, "Neutral customer sentiment detected."),
        "NEGATIVE": (0, "Negative customer sentiment detected."),
    }

    @classmethod
    def calculate_score(
        cls,
        lead_id: str,
        crm_lead: dict[str, Any] | None = None,
        intelligence_records: list[dict[str, Any]] | None = None,
        tasks: list[dict[str, Any]] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Calculate deterministic lead score and factors.
        """
        current_time = now or datetime.now(timezone.utc)
        records = intelligence_records or []
        crm = crm_lead or {}
        open_tasks = tasks or []

        # Find latest valid analyzed intelligence record
        analyzed_records = [
            r for r in records
            if r.get("classification_status", "SUCCESS") == "SUCCESS" and r.get("intent_category")
        ]
        # Sort chronologically by received_timestamp, analyzed_at, or created_at
        analyzed_records.sort(
            key=lambda r: r.get("received_timestamp") or r.get("analyzed_at") or r.get("created_at") or "",
            reverse=True,
        )
        latest_record = analyzed_records[0] if analyzed_records else None

        # 1. Customer Intent (Max 30)
        intent_score = 0
        intent_category = None
        intent_explanation = "No inbound email classified yet."
        if latest_record:
            intent_category = str(latest_record.get("intent_category", "OTHER")).upper()
            points, explanation = cls.INTENT_POINTS.get(
                intent_category, (5, "General or unrecognized inquiry.")
            )
            intent_score = points
            intent_explanation = explanation

        # 2. Sentiment (Max 20)
        sentiment_score = 0
        sentiment_val = None
        sentiment_explanation = "No sentiment analysis available."
        if latest_record:
            sentiment_val = str(latest_record.get("sentiment", "NEUTRAL")).upper()
            points, explanation = cls.SENTIMENT_POINTS.get(
                sentiment_val, (10, "Neutral sentiment detected.")
            )
            sentiment_score = points
            sentiment_explanation = explanation

        # 3. Engagement and Response Activity (Max 15)
        # Avoid double-counting: count distinct message IDs
        distinct_message_ids = {
            r.get("message_id")
            for r in records
            if r.get("message_id")
        }
        msg_count = len(distinct_message_ids)
        if msg_count >= 3:
            engagement_score = 15
            engagement_explanation = f"High engagement with {msg_count} distinct inbound messages."
        elif msg_count == 2:
            engagement_score = 10
            engagement_explanation = "Moderate engagement with 2 distinct inbound messages."
        elif msg_count == 1:
            engagement_score = 6
            engagement_explanation = "Initial engagement with 1 inbound message."
        else:
            engagement_score = 0
            engagement_explanation = "No inbound communications recorded yet."

        # 4. Budget and Buying Signals (Max 15)
        budget_score = 0
        budget_notes = []

        # CRM Budget
        crm_budget = str(crm.get("budget") or "").strip()
        has_crm_budget = bool(
            crm_budget and crm_budget.lower() not in ("none", "0", "$0", "n/a", "no", "false")
        )
        if has_crm_budget:
            budget_score += 8
            budget_notes.append(f"Budget indicated in CRM ({crm_budget}).")

        # Intelligence extracted info
        if latest_record:
            extracted = latest_record.get("extracted_information")
            if isinstance(extracted, str):
                try:
                    extracted = json.loads(extracted)
                except Exception:
                    extracted = {}
            if isinstance(extracted, dict):
                mentioned_budget = str(extracted.get("mentioned_budget") or "").strip()
                if mentioned_budget and mentioned_budget.lower() not in ("none", "null", ""):
                    budget_score += 4
                    budget_notes.append(f"Explicit budget mentioned in email ({mentioned_budget}).")

                commitments = extracted.get("customer_commitments") or []
                meeting_dates = extracted.get("requested_meeting_dates") or []
                if commitments or meeting_dates:
                    budget_score += 3
                    budget_notes.append("Customer commitments or specific meeting dates provided.")

        budget_score = min(15, budget_score)
        budget_explanation = " ".join(budget_notes) if budget_notes else "No specific budget or buying signals detected."

        # 5. Follow-up Urgency (Max 10)
        urgency_score = 0
        urgency_explanation = "No urgent follow-up required."

        # Check open follow-up tasks
        active_priorities = [
            t.get("priority", "MEDIUM")
            for t in open_tasks
            if t.get("status") in ("SCHEDULED", "IN_PROGRESS")
        ]
        if "URGENT" in active_priorities:
            urgency_score = 10
            urgency_explanation = "Urgent follow-up task is currently open."
        elif "HIGH" in active_priorities:
            urgency_score = 8
            urgency_explanation = "High priority follow-up task is currently open."
        elif "MEDIUM" in active_priorities:
            urgency_score = 5
            urgency_explanation = "Standard follow-up task is currently open."
        elif "LOW" in active_priorities:
            urgency_score = 3
            urgency_explanation = "Low priority follow-up task is currently open."
        else:
            # Check latest intelligence timeline mention
            if latest_record:
                extracted = latest_record.get("extracted_information")
                if isinstance(extracted, str):
                    try:
                        extracted = json.loads(extracted)
                    except Exception:
                        extracted = {}
                if isinstance(extracted, dict):
                    timeline = str(extracted.get("mentioned_timeline") or "").lower()
                    if any(w in timeline for w in ("asap", "urgent", "immediate", "today", "tomorrow")):
                        urgency_score = 8
                        urgency_explanation = f"Urgent timeline mentioned in email: '{timeline}'."
                    elif timeline:
                        urgency_score = 5
                        urgency_explanation = f"Timeline mentioned in email: '{timeline}'."

        urgency_score = min(10, urgency_score)

        # 6. Recency of Interaction (Max 10)
        # Determine latest interaction timestamp
        timestamps = []
        if latest_record:
            t = _parse_iso_to_utc(
                latest_record.get("received_timestamp")
                or latest_record.get("analyzed_at")
                or latest_record.get("created_at")
            )
            if t:
                timestamps.append(t)
        crm_ts = _parse_iso_to_utc(crm.get("timestamp"))
        if crm_ts:
            timestamps.append(crm_ts)

        recency_score = 0
        recency_explanation = "No recent interaction on record."
        if timestamps:
            latest_interaction = max(timestamps)
            delta_days = (current_time - latest_interaction).total_seconds() / 86400.0
            if delta_days <= 1.0:
                recency_score = 10
                recency_explanation = "Interaction within the last 24 hours."
            elif delta_days <= 3.0:
                recency_score = 8
                recency_explanation = "Interaction within the last 3 days."
            elif delta_days <= 7.0:
                recency_score = 6
                recency_explanation = "Interaction within the last 7 days."
            elif delta_days <= 14.0:
                recency_score = 4
                recency_explanation = "Interaction within the last 14 days."
            elif delta_days <= 30.0:
                recency_score = 2
                recency_explanation = "Interaction within the last 30 days."
            else:
                recency_score = 0
                recency_explanation = f"Last interaction was {int(delta_days)} days ago."

        # Total Calculation
        total_score = (
            intent_score
            + sentiment_score
            + engagement_score
            + budget_score
            + urgency_score
            + recency_score
        )
        total_score = max(0, min(100, total_score))

        # Tier assignment
        if total_score >= 75:
            tier: ScoreTier = "HOT"
        elif total_score >= 40:
            tier = "WARM"
        else:
            tier = "COLD"

        # Complaint attention flag: Separate flag so complaint is not automatically cold
        complaint_flag = False
        if intent_category == "COMPLAINT":
            complaint_flag = True
        elif sentiment_val == "NEGATIVE" and latest_record:
            summary = str(latest_record.get("summary") or "").lower()
            if "complaint" in summary or "issue" in summary or "dissatisfied" in summary:
                complaint_flag = True

        factors_detail = {
            "customer_intent": {
                "score": intent_score,
                "max": 30,
                "category": intent_category,
                "explanation": intent_explanation,
            },
            "sentiment": {
                "score": sentiment_score,
                "max": 20,
                "sentiment": sentiment_val,
                "explanation": sentiment_explanation,
            },
            "engagement": {
                "score": engagement_score,
                "max": 15,
                "message_count": msg_count,
                "distinct_messages": msg_count,
                "explanation": engagement_explanation,
            },
            "budget": {
                "score": budget_score,
                "max": 15,
                "crm_budget": crm.get("budget"),
                "explanation": budget_explanation,
            },
            "budget_and_buying_signals": {
                "score": budget_score,
                "max": 15,
                "crm_budget": crm.get("budget"),
                "explanation": budget_explanation,
            },
            "follow_up_urgency": {
                "score": urgency_score,
                "max": 10,
                "explanation": urgency_explanation,
            },
            "recency": {
                "score": recency_score,
                "max": 10,
                "explanation": recency_explanation,
            },
            "complaint_attention_flag": complaint_flag,
        }

        return {
            "lead_id": lead_id,
            "score": total_score,
            "tier": tier,
            "factors": factors_detail,
            "complaint_attention_flag": complaint_flag,
            "version": ALGORITHM_VERSION,
        }


LeadScoringEngine = DeterministicLeadScorer
lead_scoring_engine = DeterministicLeadScorer()


def compute_lead_score(
    lead_id: str,
    crm_lead: dict[str, Any] | None = None,
    intelligence_records: list[dict[str, Any]] | None = None,
    tasks: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    return DeterministicLeadScorer.calculate_score(
        lead_id=lead_id,
        crm_lead=crm_lead,
        intelligence_records=intelligence_records,
        tasks=tasks,
        now=now,
    )

