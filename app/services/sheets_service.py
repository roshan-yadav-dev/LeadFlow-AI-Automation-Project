
import os
import logging

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("leadflow")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets"
]


def get_sheets_service():
    credentials = Credentials.from_service_account_file(
        os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
        scopes=SCOPES
    )

    return build(
        "sheets",
        "v4",
        credentials=credentials
    )



def append_lead(lead):
    service = get_sheets_service()
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")

    values = [[
        lead.get("lead_id", ""),
        lead.get("timestamp", ""),
        lead.get("name", ""),
        lead.get("email", ""),
        lead.get("phone", ""),
        lead.get("company", ""),
        lead.get("service", ""),
        lead.get("requirements", ""),
        lead.get("ai_subject", ""),
        lead.get("ai_response", ""),
        lead.get("email_status", "PENDING"),
        lead.get("lead_status", "NEW"),
        lead.get("error_message", ""),
        lead.get("budget", ""),
        lead.get("consent", False),
        lead.get("ai_status", "PENDING"),
        lead.get("lead_summary", ""),
        lead.get("suggested_next_step", "")
    ]]

    if len(values[0]) != 18:
        raise ValueError("Expected exactly 18 lead fields")

    result = service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!A:R",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": values}
    ).execute()

    logger.info("Lead saved to Google Sheets: %s", lead.get("lead_id"))

    return result

###Phase 2###


def find_lead_by_email(email: str):

    service = get_sheets_service()

    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")

    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!D2:D"
    ).execute()

    rows = result.get("values", [])

    normalized_email = email.strip().lower()

    for row_number, row in enumerate(rows, start=2):

        if row and str(row[0]).strip().lower() == normalized_email:
            return {
                "exists": True,
                "row": row_number
            }

    return {
        "exists": False,
        "row": None
    }

def get_lead_by_email(email: str) -> dict | None:
    """
    Retrieve CRM lead details using a normalized email address.
    Returns None when no matching lead exists.
    """
    match = find_lead_by_email(email)

    if not match["exists"]:
        return None

    service = get_sheets_service()
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")
    row_number = match["row"]

    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"Sheet1!A{row_number}:R{row_number}"
    ).execute()

    rows = result.get("values", [])

    if not rows:
        return None

    row = rows[0]

    # Safely handle missing trailing cells.
    row += [""] * (18 - len(row))

    return {
        "lead_id": row[0],
        "name": row[2],
        "email": str(row[3]).strip().lower(),
        "phone": row[4],
        "company": row[5],
        "service": row[6],
        "requirements": row[7],
        "email_status": row[10],
        "lead_status": row[11],
        "budget": row[13],
        "consent": row[14],
    }


def list_leads_for_matching() -> list[dict]:
    """Read the CRM once and return the fields needed for Gmail matching."""
    service = get_sheets_service()
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!A2:R",
    ).execute()

    leads: list[dict] = []
    for sheet_row, source_row in enumerate(result.get("values", []), start=2):
        row = list(source_row[:18])
        row.extend([""] * (18 - len(row)))
        lead_id = str(row[0]).strip()
        email = str(row[3]).strip().lower()
        if not lead_id:
            continue
        leads.append({
            "lead_id": lead_id,
            "name": str(row[2]).strip(),
            "email": email,
            "phone": str(row[4]).strip(),
            "company": str(row[5]).strip(),
            "service": str(row[6]).strip(),
            "requirements": str(row[7]).strip(),
            "lead_status": str(row[11]).strip(),
            "budget": str(row[13]).strip(),
            "consent": str(row[14]).strip(),
            "sheet_row": sheet_row,
        })
    return leads


def update_lead_email_status(
    lead_id: str,
    email_status: str,
    error_message: str = "",
) -> bool:
    """Update only the email status and error cells for an existing lead."""
    if email_status not in {"PENDING", "APPROVED", "SENT", "FAILED", "SKIPPED"}:
        raise ValueError("Unsupported email status")

    service = get_sheets_service()
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A2:A",
        ).execute()

        row_number = next(
            (
                index
                for index, row in enumerate(result.get("values", []), start=2)
                if row and row[0] == lead_id
            ),
            None,
        )
        if row_number is None:
            logger.warning("Unable to update email status: lead ID was not found")
            return False

        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "RAW",
                "data": [
                    {
                        "range": f"Sheet1!K{row_number}",
                        "values": [[email_status]],
                    },
                    {
                        "range": f"Sheet1!M{row_number}",
                        "values": [[error_message]],
                    },
                ],
            },
        ).execute()
    except HttpError as exc:
        http_status = getattr(getattr(exc, "resp", None), "status", None)
        logger.error(
            "Google Sheets email status update failed with HTTP status %s",
            http_status,
        )
        return False

    return True


def update_lead_crm_row(lead_id: str, lead: dict) -> bool:
    """Update all 18 CRM fields for an existing lead identified by lead_id."""
    service = get_sheets_service()
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")

    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!A2:A",
    ).execute()

    row_number = next(
        (
            index
            for index, row in enumerate(result.get("values", []), start=2)
            if row and row[0] == lead_id
        ),
        None,
    )
    if row_number is None:
        logger.warning("Unable to update lead CRM row: lead ID '%s' was not found", lead_id)
        return False

    values = [[
        lead_id,
        lead.get("timestamp", ""),
        lead.get("name", ""),
        lead.get("email", ""),
        lead.get("phone", ""),
        lead.get("company", ""),
        lead.get("service", ""),
        lead.get("requirements", ""),
        lead.get("ai_subject", ""),
        lead.get("ai_response", ""),
        lead.get("email_status", "PENDING"),
        lead.get("lead_status", "NEW"),
        lead.get("error_message", ""),
        lead.get("budget", ""),
        lead.get("consent", False),
        lead.get("ai_status", "PENDING"),
        lead.get("lead_summary", ""),
        lead.get("suggested_next_step", "")
    ]]

    if len(values[0]) != 18:
        raise ValueError("Expected exactly 18 lead fields")

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"Sheet1!A{row_number}:R{row_number}",
        valueInputOption="RAW",
        body={"values": values}
    ).execute()

    logger.info("Updated lead CRM row in Google Sheets: %s (row %d)", lead_id, row_number)
    return True


def update_lead_ai_response(
    lead_id: str,
    ai_subject: str,
    ai_response: str,
    ai_status: str,
    lead_summary: str = "",
    suggested_next_step: str = "",
    error_message: str = "",
) -> bool:
    """Update AI personalization fields (columns I, J, M, P, Q, R) for an existing lead."""
    service = get_sheets_service()
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")

    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range="Sheet1!A2:A",
    ).execute()

    row_number = next(
        (
            index
            for index, row in enumerate(result.get("values", []), start=2)
            if row and row[0] == lead_id
        ),
        None,
    )
    if row_number is None:
        logger.warning("Unable to update AI response: lead ID '%s' was not found", lead_id)
        return False

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "RAW",
            "data": [
                {"range": f"Sheet1!I{row_number}", "values": [[ai_subject]]},
                {"range": f"Sheet1!J{row_number}", "values": [[ai_response]]},
                {"range": f"Sheet1!M{row_number}", "values": [[error_message]]},
                {"range": f"Sheet1!P{row_number}", "values": [[ai_status]]},
                {"range": f"Sheet1!Q{row_number}", "values": [[lead_summary]]},
                {"range": f"Sheet1!R{row_number}", "values": [[suggested_next_step]]},
            ],
        },
    ).execute()

    logger.info("Updated AI response in Google Sheets for lead %s (row %d)", lead_id, row_number)
    return True


def append_or_update_lead(lead: dict) -> dict:
    """
    Append a new lead if no CRM row exists with the email,
    or update the existing CRM row with the new data.
    """
    email = str(lead.get("email", "")).strip().lower()
    existing = find_lead_by_email(email)

    if existing["exists"]:
        row_number = existing["row"]
        service = get_sheets_service()
        spreadsheet_id = os.getenv("GOOGLE_SHEET_ID")

        res = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"Sheet1!A{row_number}:R{row_number}",
        ).execute()
        rows = res.get("values", [])
        existing_lead_id = rows[0][0] if (rows and rows[0]) else lead.get("lead_id", "")
        lead_id = existing_lead_id or lead.get("lead_id", "")
        lead["lead_id"] = lead_id

        success = update_lead_crm_row(lead_id, lead)
        if not success:
            raise RuntimeError(f"Failed to update existing CRM row for lead '{lead_id}'")
        return {"action": "UPDATED", "lead_id": lead_id, "row": row_number}

    append_result = append_lead(lead)
    return {"action": "CREATED", "lead_id": lead.get("lead_id"), "result": append_result}
