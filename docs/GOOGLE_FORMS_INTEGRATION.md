# LeadFlow AI — Google Forms Integration Guide

This guide details how to integrate **Google Forms** with LeadFlow AI for automated, AI-personalized lead capture, Google Sheets CRM synchronization, and deterministic lead scoring.

---

## Architecture Overview

```
Google Form Submission
       │
       ▼ (Automatic Google Form record)
Linked Google Spreadsheet ("Form Responses 1")
       │
       ▼ (Installable onFormSubmit Trigger)
Google Apps Script (scripts/google_forms_apps_script.js)
       │
       ▼ HTTPS POST + X-Webhook-Secret
LeadFlow AI Backend (`/api/v1/leads/webhook/forms`)
       ├── 1. Webhook Authentication Verification
       ├── 2. Persistent Idempotency Check (SQLite `lead_submissions`)
       ├── 3. Dynamic Field Mapping & Normalization
       ├── 4. Groq LLM Email Personalization (`openai/gpt-oss-20b`)
       ├── 5. Google Sheets CRM Row Write / Update (18 columns)
       ├── 6. Event Emission (`LEAD_CREATED`) → Deterministic Scoring (0-100)
       └── 7. Safety Guard: No automatic email dispatch
```

---

## Step 1: Google Form Creation

1. Open [Google Forms](https://forms.google.com/) and create a new form (e.g., *"Business Enquiry Form"*).
2. Add the following recommended fields:
   - **Full Name** (Short answer, Required)
   - **Email Address** (Short answer, Required, response validation: Email)
   - **Phone Number** (Short answer, Optional)
   - **Company / Organization** (Short answer, Optional)
   - **Service Requested** (Dropdown or Short answer, e.g., *"Web Development"*, *"Cloud Migration"*, *"AI Consulting"*)
   - **Project Requirements** (Paragraph, Required, min 10 characters)
   - **Budget Range** (Short answer or Dropdown, e.g., *"$5,000 - $10,000"*)
   - **Email Consent** (Multiple choice or Checkbox, e.g., *"I agree to receive communications regarding my inquiry"* - Required for email outreach)

> [!NOTE]
> LeadFlow AI's normalizer dynamically recognizes alternative question labels (e.g., `"Your Name"` vs `"Full Name"`, `"Project Details"` vs `"Requirements"`, `"Interested Service"` vs `"Service"`).

---

## Step 2: Link the Response Spreadsheet

1. In your Google Form, switch to the **Responses** tab.
2. Click **Link to Sheets** (the green spreadsheet icon).
3. Select **Create a new spreadsheet** (e.g., *"Business Enquiry Form (Responses)"*), then click **Create**.
4. The spreadsheet will open with a sheet named `Form Responses 1`.

---

## Step 3: Add Google Apps Script

1. In the linked Google Sheet, click **Extensions** > **Apps Script**.
2. Rename the project in the top left from *"Untitled project"* to **LeadFlow Webhook Dispatcher**.
3. Clear the default `myFunction()` code in `Code.gs`.
4. Copy the entire contents of [scripts/google_forms_apps_script.js](file:///home/roshan/LeadFlow-AI/scripts/google_forms_apps_script.js) and paste it into the editor.
5. Click **Save** (the floppy disk icon or `Ctrl+S` / `Cmd+S`).

---

## Step 4: Configure Script Properties (Secure Credentials)

> [!CAUTION]
> Never hardcode secrets or webhook URLs directly into the script code. Always use Google Apps Script Script Properties.

1. In the left navigation bar of the Apps Script editor, click the **Project Settings** gear icon.
2. Scroll to the **Script Properties** section at the bottom.
3. Click **Add script property** and add the following two properties:

| Property Name | Example Value | Description |
| :--- | :--- | :--- |
| `LEADFLOW_WEBHOOK_URL` | `https://your-domain.com/api/v1/leads/webhook/forms` | URL to your LeadFlow AI backend webhook endpoint |
| `LEADFLOW_WEBHOOK_SECRET` | *(Your `WEBHOOK_SECRET` from `.env`)* | Shared secret matching `WEBHOOK_SECRET` in LeadFlow AI |

4. Click **Save script properties**.

---

## Step 5: Install the `onFormSubmit` Trigger

1. In the left navigation bar, click the **Triggers** clock icon.
2. Click **+ Add Trigger** (in the bottom-right corner).
3. Configure the trigger modal as follows:
   - **Choose which function to run:** `handleFormSubmit`
   - **Choose which deployment should run:** `Head`
   - **Select event source:** `From spreadsheet`
   - **Select event type:** `On form submit`
   - **Failure notification settings:** `Notify me daily` (or `Notify me immediately`)
4. Click **Save**.
5. Google will display an **Authorization Required** dialog. Select your Google account, click **Advanced** > **Go to LeadFlow Webhook Dispatcher (unsafe)**, and click **Allow** to grant spreadsheet and external network access permissions (`UrlFetchApp`).

---

## Step 6: Run a Test Submission

1. Go back to your Google Form.
2. Click the **Preview** (eye icon) to open the live form.
3. Fill out the form with test data:
   - Full Name: `Jane Doe`
   - Email Address: `jane.test@example.com`
   - Company: `Acme Corporation`
   - Service Requested: `AI Automation`
   - Project Requirements: `Need an automated lead qualification system with CRM sync.`
   - Budget Range: `$10,000 - $25,000`
   - Email Consent: `Yes, I agree`
4. Click **Submit**.

---

## Step 7: Verify Results

### 1. Verification in Google Apps Script
- In Apps Script, click **Executions** in the left menu.
- You will see the execution record for `handleFormSubmit`.
- Status should display **Completed** with log:
  ```
  Dispatching submission ... to LeadFlow AI webhook...
  LeadFlow AI webhook succeeded with HTTP 200 for submission ...
  ```

### 2. Verification in LeadFlow AI CRM Sheet
Open your configured LeadFlow AI CRM Google Sheet (`GOOGLE_SHEET_ID` in `.env`). Check the 18 columns in `Sheet1`:

| Column | Field | Expected Value |
| :--- | :--- | :--- |
| `A` | `lead_id` | `LF-XXXXXXXXXXXX` |
| `B` | `timestamp` | ISO UTC timestamp |
| `C` | `name` | `Jane Doe` |
| `D` | `email` | `jane.test@example.com` |
| `E`–`H` | Contact & Service | Phone, Company, Service, Requirements |
| `I` | `ai_subject` | Personalized email subject generated by Groq |
| `J` | `ai_response` | Personalized email body generated by Groq |
| `K` | `email_status` | `PENDING` (Never auto-dispatched) |
| `L` | `lead_status` | `NEW` |
| `N` | `budget` | `$10,000 - $25,000` |
| `O` | `consent` | `True` |
| `P` | `ai_status` | `SUCCESS` |
| `Q` | `lead_summary` | Executive business summary generated by Groq |
| `R` | `suggested_next_step` | Recommended next action generated by Groq |

### 3. Verification in LeadFlow AI Dashboard
- Log in to the LeadFlow AI dashboard (`http://localhost:5173`).
- Open **Leads**: Observe `Jane Doe` ranked with hot/warm score badge.
- Open **Audit Logs**: View `LEAD_CREATED` event from `google_forms_webhook`.
- Open **Scoring**: View transparent 100-point factor breakdown.

---

## Idempotency & Duplicate Handling

- **Stable Submission ID:** Generated as `<spreadsheetId>_<sheetId>_row_<rowNumber>`.
- **Duplicate Prevention:** If the trigger fires multiple times for the same submission row, LeadFlow AI detects the existing `submission_id` in SQLite `lead_submissions`, records the duplicate event, and returns HTTP `200` without duplicating AI generation or CRM rows.
- **Repeat Submissions:** If an existing contact submits a *new* form response (different row / submission ID), LeadFlow AI associates the submission with the existing CRM lead and updates the CRM row rather than appending a redundant contact row.

---

## Safety & Human-in-the-Loop Policies

> [!IMPORTANT]
> - **Explicit Consent Mandatory:** If a lead does not provide clear consent, `consent` is recorded as `False`.
> - **Zero Auto-Dispatch:** Google Form submissions **never** automatically send emails to customers upon form submission. The email status remains `PENDING` until reviewed and authorized.
> - **Approval Isolation:** Human approval grants authorization; direct customer outreach requires deliberate operator review.

---

## Troubleshooting

| Issue | Cause | Resolution |
| :--- | :--- | :--- |
| HTTP 401 Unauthorized | Missing or incorrect `X-Webhook-Secret` header | Verify `LEADFLOW_WEBHOOK_SECRET` in Script Properties matches `WEBHOOK_SECRET` in `.env`. |
| HTTP 422 Unprocessable Content | Invalid email format or requirements under 10 characters | Check form validation rules: ensure email is valid and requirements contains at least 10 characters. |
| HTTP 502 Bad Gateway | Google Sheets API rate limit or permission error | Verify `GOOGLE_SERVICE_ACCOUNT_FILE` has Editor access to the CRM sheet (`GOOGLE_SHEET_ID`). Transient errors are automatically enqueued in `automation_jobs` for retry. |
| Trigger not firing | Trigger configured as simple trigger instead of installable trigger | Simple triggers (`onEdit`, `onOpen`) cannot access network resources. Install via Apps Script **Triggers** (+ Add Trigger) selecting `On form submit`. |
