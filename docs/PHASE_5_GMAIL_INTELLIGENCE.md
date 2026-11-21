# Phase 5: Gmail Lead Intelligence

## Architecture

Phase 5 operates only on messages already synchronized into
`GMAIL_DB_FILE`. The manual flow is:

1. Synchronize Gmail using the existing sync endpoint.
2. Load CRM rows A:R in one Google Sheets request and match sender addresses.
3. Keep unmatched, ambiguous, and filtered messages in the intelligence store
   for audit; do not send them to Groq.
4. Analyze only matched messages when the analyze endpoint is explicitly
   called.
5. Save classification and each analysis attempt to a separate SQLite
   database.

The workflow is not started during application startup or ordinary Gmail
synchronization. Gmail messages and Google Sheets records are not modified;
the workflow does not send messages or update CRM statuses.

## CRM Matching

`list_leads_for_matching()` reads `Sheet1!A2:R` once per matching operation.
Email addresses are trimmed and lowercased before indexing. Gmail sender
addresses are validated and normalized the same way. A unique address maps
to its `Lead_ID` and CRM details; no exact match is `UNMATCHED`. More than one
CRM row for an address is `AMBIGUOUS` and does not select a lead. Invalid CRM
addresses are excluded from the index. The existing
`find_lead_by_email()` and `get_lead_by_email()` interfaces remain available.

## Inbound Message Filtering

Filtered messages retain an intelligence record with an `ignore_reason`.
Filtering excludes:

- Messages with a missing or invalid sender address.
- Messages from `GMAIL_SENDER_EMAIL` or carrying Gmail's `SENT` label.
- Obvious no-reply, postmaster, bounce, and mailer-daemon addresses.
- Messages carrying `SPAM` or `TRASH` labels.
- Mailing-list headers (`List-Id`, `List-Post`, or `List-Unsubscribe`) and
  bulk/list/junk precedence headers.
- Messages indicating automatic submission or auto-reply headers.

The filter is intentionally conservative: categories such as Promotions and
Updates alone are not sufficient to discard a message. The original inbox
records, body, labels, and headers are not changed.

## SQLite Schema and History

`GMAIL_INTELLIGENCE_DB_FILE` defaults to
`credentials/gmail_intelligence.sqlite3`, separate from `GMAIL_DB_FILE`.
`gmail_message_intelligence` has one unique row per Gmail message, including
the lead association, received timestamp, match and classification statuses,
ignore reason, intent, sentiment, confidence, summary, extracted information,
action items, suggested next step, error, and timestamps. Indexes support
lead, status, intent, and sentiment queries.

`gmail_intelligence_analysis_history` appends every successful, failed, or
skipped analysis attempt. SQLite transactions, a busy timeout, WAL mode, and
an atomic analysis claim protect concurrent processing. A stale analysis
claim can be retried after 15 minutes. Existing inbox databases receive an
additive `headers` column migration; existing messages and sync state are
preserved.

Match statuses are `MATCHED`, `UNMATCHED`, `IGNORED`, and `AMBIGUOUS`.
Classification statuses are `PENDING`, `ANALYZING`, `SUCCESS`, `FAILED`, and
`SKIPPED`. Failed analyses can be retried. A forced reanalysis records a new
history entry; if it fails, the previous structured result remains stored.

## AI Classification

The classifier reuses the configured Groq client and `GROQ_MODEL` (default
`openai/gpt-oss-20b`). Intent categories are:

- `INTERESTED`, `NOT_INTERESTED`, `FOLLOW_UP`, `MEETING_REQUEST`
- `PRICING_INQUIRY`, `INFORMATION_REQUEST`, `NEGOTIATION`, `COMPLAINT`
- `OUT_OF_OFFICE`, `OTHER`

Sentiment is `POSITIVE`, `NEUTRAL`, `NEGATIVE`, or `MIXED`. The structured
result includes confidence, a concise summary, main intent, important
requirements, mentioned budget and timeline, requested meeting dates,
customer questions and commitments, action items, and a suggested next step.
Pydantic validates the model response before persistence. Missing information
must be represented as empty lists or nulls, and unclear intent should have
low confidence. Quoted prior content must not be interpreted as a new
customer commitment.

## Prompt-Injection and Data Safeguards

Email subject, headers, body, snippets, and quoted content are untrusted data.
The classifier receives email fields as JSON in the user message, with
instructions kept in a separate system message. It has no tools and cannot
visit URLs. Its only output is validated classification data; it cannot send
email, modify CRM data, or invoke application operations. Email bodies are not
written to logs. Analysis sends at most
`GMAIL_INTELLIGENCE_MAX_BODY_CHARS` characters (default 12000) to the existing
Groq provider.

All new intelligence and communication-history endpoints require the existing
`X-Webhook-Secret` authentication. Use HTTPS when exposing the application
outside localhost.

## API Endpoints

All endpoints below use the existing `X-Webhook-Secret` header. The examples
use environment-variable references only; do not put secret values in source
control or documentation.

### Match synchronized messages

```bash
curl -X POST http://localhost:8001/api/v1/gmail/intelligence/match \
  -H "X-Webhook-Secret: $WEBHOOK_SECRET"
```

Example response:

```json
{
  "matched": 12,
  "unmatched": 4,
  "ambiguous": 1,
  "ignored": 8,
  "processed": 25
}
```

### Analyze a bounded batch

```bash
curl -X POST http://localhost:8001/api/v1/gmail/intelligence/analyze \
  -H "X-Webhook-Secret: $WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"batch_size": 10, "force_reanalysis": false}'
```

`batch_size` must be between 1 and 100 and is capped by
`GMAIL_INTELLIGENCE_MAX_BATCH_SIZE`. If the request body is omitted,
`GMAIL_INTELLIGENCE_BATCH_SIZE` is used. Already-successful messages are
skipped unless `force_reanalysis` is true.

Example response:

```json
{"requested": 10, "succeeded": 8, "failed": 1, "skipped": 1}
```

### Overview

```bash
curl http://localhost:8001/api/v1/gmail/intelligence/overview \
  -H "X-Webhook-Secret: $WEBHOOK_SECRET"
```

Returns synchronized, eligible, matched, unmatched, ambiguous, ignored,
analyzed, pending, and failed counts plus intent and sentiment counts. It
does not return email bodies.

Example response:

```json
{
  "total_synchronized_messages": 25,
  "total_eligible_messages": 17,
  "matched_messages": 12,
  "unmatched_messages": 4,
  "ignored_messages": 8,
  "ambiguous_messages": 1,
  "analyzed_messages": 8,
  "pending_analyses": 4,
  "failed_analyses": 0,
  "intent_category_counts": {"PRICING_INQUIRY": 3, "OTHER": 5},
  "sentiment_counts": {"NEUTRAL": 6, "POSITIVE": 2}
}
```

### Message intelligence detail and reanalysis

```bash
curl http://localhost:8001/api/v1/gmail/intelligence/messages/GMAIL_MESSAGE_ID \
  -H "X-Webhook-Secret: $WEBHOOK_SECRET"

curl -X POST \
  http://localhost:8001/api/v1/gmail/intelligence/messages/GMAIL_MESSAGE_ID/reanalyze \
  -H "X-Webhook-Secret: $WEBHOOK_SECRET"
```

The detail response includes the stored classification and analysis history,
not the email body. Reanalysis requires an existing synchronized message, a
matched intelligence record, and an existing associated CRM lead.

Example detail response:

```json
{
  "message_id": "MSG_ID",
  "lead_id": "LF-LEAD_ID",
  "match_status": "MATCHED",
  "ignore_reason": null,
  "classification_status": "SUCCESS",
  "intent_category": "PRICING_INQUIRY",
  "sentiment": "NEUTRAL",
  "confidence": 0.9,
  "summary": "The customer asked about pricing.",
  "extracted_information": {
    "main_intent": "Ask about pricing.",
    "important_requirements": [],
    "mentioned_budget": null,
    "mentioned_timeline": null,
    "requested_meeting_dates": [],
    "customer_questions": ["What does it cost?"],
    "customer_commitments": []
  },
  "action_items": ["Prepare a pricing overview."],
  "suggested_next_step": "Share pricing information.",
  "analysis_error": null,
  "analyzed_at": "2026-01-01T00:00:00+00:00",
  "created_at": "2026-01-01T00:00:00+00:00",
  "updated_at": "2026-01-01T00:00:00+00:00",
  "analysis_history": []
}
```

### Lead communication history

```bash
curl "http://localhost:8001/api/v1/leads/LEAD_ID/communications?page=1&page_size=25" \
  -H "X-Webhook-Secret: $WEBHOOK_SECRET"
```

Returns the lead ID, name and email, total matched messages, latest message
timestamp, and a page of message metadata, snippets, classification, summary,
and next action. Full HTML and plain-text bodies are not included.

Example response:

```json
{
  "lead_id": "LF-LEAD_ID",
  "lead_name": "Example Customer",
  "lead_email": "customer@example.com",
  "total_matched_messages": 1,
  "latest_message_timestamp": "2026-01-01T00:00:00+00:00",
  "page": 1,
  "page_size": 25,
  "messages": [
    {
      "message_id": "MSG_ID",
      "received_timestamp": "2026-01-01T00:00:00+00:00",
      "subject": "Pricing question",
      "sender": "customer@example.com",
      "snippet": "Could you share pricing?",
      "intent_category": "PRICING_INQUIRY",
      "sentiment": "NEUTRAL",
      "summary": "The customer asked about pricing.",
      "suggested_next_action": "Share pricing information.",
      "analysis_status": "SUCCESS"
    }
  ]
}
```

## Errors and Retries

Google Sheets failures stop the matching operation and return a safe gateway
error. If CRM context cannot be loaded during analysis, affected matched
messages are recorded as failed without being sent to Groq. Gmail
synchronization remains independent of matching and Groq. Groq client retries
use the existing `GROQ_MAX_RETRIES` configuration. Per-message classification
failures are recorded without stopping the rest of the batch; they remain
eligible on a later analyze request. OAuth credentials, API keys, and raw
exception details are not included in API error responses.

## Configuration

Use the existing project configuration:

- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_FILE`
- `GROQ_API_KEY`
- `GROQ_MODEL`
- `GROQ_TIMEOUT`
- `GROQ_MAX_RETRIES`
- `GMAIL_SENDER_EMAIL`
- `GMAIL_DB_FILE`

Phase 5 adds:

- `GMAIL_INTELLIGENCE_DB_FILE`
- `GMAIL_INTELLIGENCE_BATCH_SIZE`
- `GMAIL_INTELLIGENCE_MAX_BATCH_SIZE`
- `GMAIL_INTELLIGENCE_MAX_BODY_CHARS`

No new package dependency is required. Existing Gmail OAuth configuration and
scopes are unchanged.

## Automated Tests

Run the offline suite with mocked Sheets and Groq interactions:

```bash
venv/bin/python -m compileall -q app
venv/bin/pytest -q
```

Tests use temporary SQLite files and do not send Gmail messages or write to
production Google Sheets.

## Manual End-to-End Testing

1. Configure the existing environment variables and Google credentials using
   your normal secure local process.
2. Start the server:

   ```bash
   venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
   ```
3. Verify `/health` and the existing `/api/v1/gmail/status` endpoint.
4. Complete Gmail OAuth only if the existing status endpoint reports that
   Gmail is not connected.
5. Synchronize messages with `POST /api/v1/gmail/sync`.
6. Trigger matching with `POST /api/v1/gmail/intelligence/match`.
7. Review matches, ambiguous addresses, and ignore reasons through the
   intelligence detail and overview endpoints.
8. Trigger analysis with a small `batch_size`; inspect the overview and
   matched-message detail endpoint.
9. Inspect lead history at `/api/v1/leads/{lead_id}/communications`.
10. Use `force_reanalysis` or the explicit reanalysis endpoint only when a new
    AI call is intended.

Use the configured `X-Webhook-Secret` header with all intelligence endpoints.
Groq analysis, Gmail processing, and spreadsheet access in the manual flow
contact real configured services. The automated test suite does not verify
those production integrations.

## Known Limitations

- Matching is exact sender-email matching; aliases and forwarded messages are
  not inferred.
- Duplicate CRM email addresses are intentionally ambiguous and require CRM
  cleanup before they can be analyzed.
- Messages must first be present in the synchronized inbox database.
- Classification is message-level; quoted-history interpretation is guided
  by the prompt but cannot be guaranteed perfectly.
- SQLite and sync locking remain local to one host/application process.
- The overview reports eligibility after a match operation has populated the
  intelligence records.
- No production Gmail sync, Groq analysis, or Google Sheets access was run as
  part of implementation validation.
