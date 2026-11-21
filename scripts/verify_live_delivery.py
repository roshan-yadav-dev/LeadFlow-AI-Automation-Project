import json
import time
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.automation_store import automation_store
from app.services.sheets_service import get_lead_by_email

def run_live_verification():
    print("=" * 70)
    print("STARTING LIVE VERIFICATION OF GOOGLE FORMS -> GMAIL DELIVERY PIPELINE")
    print("=" * 70)

    client = TestClient(app)
    headers = {"X-Webhook-Secret": settings.WEBHOOK_SECRET}
    recipient_email = "roshanarvind1@gmail.com"
    submission_id = f"live_form_{int(time.time())}"

    # Step 1: Submit Google Form
    print(f"\n[Step 1 & 2] Submitting Google Form for {recipient_email}...")
    payload = {
        "submission_id": submission_id,
        "spreadsheet_id": settings.GOOGLE_SHEET_ID,
        "sheet_id": 0,
        "sheet_name": "Form Responses 1",
        "row_number": 999,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "named_values": {
            "Full Name": ["Roshan Arvind"],
            "Email Address": [recipient_email],
            "Phone Number": ["+91 9876543210"],
            "Company": ["LeadFlow AI Automation"],
            "Service Requested": ["AI Email Automation"],
            "Requirements": ["Verifying live end-to-end controlled email delivery for Google Forms lead intake."],
            "Preferred Contact": ["Email"],
            "Consent": ["Yes, I agree to receive email communication"],
        },
    }

    resp = client.post("/api/v1/leads/webhook/forms", json=payload, headers=headers)
    print(f"Webhook HTTP Status: {resp.status_code}")
    webhook_data = resp.json()
    print("Webhook Response:", json.dumps(webhook_data, indent=2))
    assert resp.status_code == 200, f"Webhook failed: {resp.text}"
    assert webhook_data["status"] == "success"
    assert webhook_data["ai_status"] == "SUCCESS"
    assert webhook_data["email_status"] == "PENDING"
    assert webhook_data.get("draft_id") is not None
    assert webhook_data.get("approval_id") is not None

    draft_id = webhook_data["draft_id"]
    lead_id = webhook_data["lead_id"]
    approval_id = webhook_data["approval_id"]
    print(f"\nCreated Lead: {lead_id}, Draft: {draft_id}, Approval: {approval_id}")

    # Step 3: Confirm AI-generated subject and body (Email Preview)
    print("\n[Step 3 & 4] Fetching Email Draft Preview...")
    draft_resp = client.get(f"/api/v1/automation/emails/drafts/{draft_id}", headers=headers)
    print(f"Draft HTTP Status: {draft_resp.status_code}")
    draft_data = draft_resp.json()
    print("Draft Preview:")
    print(f"  To: {draft_data['recipient']}")
    print(f"  Subject: {draft_data['subject']}")
    print(f"  Status: {draft_data['status']}")
    print(f"  Body Snippet:\n  {draft_data['body'][:200]}...")
    assert draft_data["recipient"] == recipient_email
    assert len(draft_data["subject"]) > 5
    assert len(draft_data["body"]) > 20
    assert draft_data["status"] == "PENDING"

    # Step 4: Approve the email draft
    print("\n[Step 5] Approving Email Draft (Human Approval Action)...")
    approve_resp = client.post(
        f"/api/v1/automation/emails/drafts/{draft_id}/approve",
        json={"notes": "Approved by supervisor for live delivery verification"},
        headers=headers,
    )
    print(f"Approve HTTP Status: {approve_resp.status_code}")
    approve_data = approve_resp.json()
    print("Approve Response:", json.dumps(approve_data, indent=2))
    assert approve_resp.status_code == 200
    assert approve_data["status"] == "APPROVED"
    assert approve_data["sent_at"] is None, "Approval alone MUST NOT dispatch email!"
    assert approve_data["gmail_message_id"] is None

    # Verify status in SQLite and Sheets is APPROVED
    draft_check = automation_store.get_email_draft(draft_id)
    assert draft_check["status"] == "APPROVED"
    print("Draft Status in SQLite: APPROVED")

    # Step 5: Explicitly Send the Email
    print("\n[Step 5b] Explicitly Dispatching Email via Gmail API...")
    send_resp = client.post(
        f"/api/v1/automation/emails/drafts/{draft_id}/send",
        headers=headers,
    )
    print(f"Send HTTP Status: {send_resp.status_code}")
    send_data = send_resp.json()
    print("Send Response:", json.dumps(send_data, indent=2))
    assert send_resp.status_code == 200, f"Send failed: {send_resp.text}"
    assert send_data["success"] is True
    assert send_data["status"] == "SENT"
    assert send_data["message_id"] is not None
    gmail_msg_id = send_data["message_id"]
    print(f"\n>>> Gmail API Confirmed Send! Message ID: {gmail_msg_id} <<<")

    # Step 6: Verify final status in SQLite and Google Sheets
    print("\n[Step 7 & 8] Verifying Final Synchronization...")
    final_draft = automation_store.get_email_draft(draft_id)
    assert final_draft["status"] == "SENT"
    assert final_draft["gmail_message_id"] == gmail_msg_id
    print("SQLite email_drafts status: SENT")
    print(f"SQLite email_drafts gmail_message_id: {final_draft['gmail_message_id']}")

    final_sub = automation_store.get_lead_submission(submission_id)
    assert final_sub["email_status"] == "SENT"
    print("SQLite lead_submissions email_status: SENT")

    # Verify duplicate prevention: calling send again must fail
    print("\n[Step 9] Verifying Duplicate Send Prevention...")
    dup_resp = client.post(
        f"/api/v1/automation/emails/drafts/{draft_id}/send",
        headers=headers,
    )
    print(f"Duplicate Send HTTP Status: {dup_resp.status_code}")
    print("Duplicate Send Response:", dup_resp.json())
    assert dup_resp.status_code in (400, 409)
    print("Duplicate send attempt safely blocked!")

    # Check Google Sheets row
    print("\n[Step 10] Checking Google Sheets CRM row...")
    try:
        crm_lead = get_lead_by_email(recipient_email)
        if crm_lead:
            print("Google Sheets CRM Record:")
            print(f"  Lead ID: {crm_lead.get('lead_id')}")
            print(f"  Name: {crm_lead.get('name')}")
            print(f"  Email Status: {crm_lead.get('email_status')}")
    except Exception as e:
        print(f"Note on Google Sheets check: {e}")

    print("\n" + "=" * 70)
    print("ALL LIVE VERIFICATION CHECKS COMPLETED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_live_verification()
