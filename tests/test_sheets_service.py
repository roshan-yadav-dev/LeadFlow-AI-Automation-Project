from types import SimpleNamespace
from unittest.mock import Mock

from googleapiclient.errors import HttpError

from app.services import sheets_service


def _sheets_api(monkeypatch):
    service = Mock()
    values = service.spreadsheets.return_value.values.return_value
    monkeypatch.setattr(sheets_service, "get_sheets_service", lambda: service)
    monkeypatch.setattr(
        sheets_service.os,
        "getenv",
        lambda name, default=None: "spreadsheet-id"
        if name == "GOOGLE_SHEET_ID"
        else default,
    )
    return service, values


def test_update_lead_email_status_only_writes_columns_k_and_m(monkeypatch):
    _, values = _sheets_api(monkeypatch)
    values.get.return_value.execute.return_value = {
        "values": [["LF-OLDER"], ["LF-TARGET"]]
    }

    updated = sheets_service.update_lead_email_status(
        "LF-TARGET",
        "FAILED",
        "Gmail is not connected.",
    )

    assert updated is True
    values.get.assert_called_once_with(
        spreadsheetId="spreadsheet-id",
        range="Sheet1!A2:A",
    )
    values.batchUpdate.assert_called_once_with(
        spreadsheetId="spreadsheet-id",
        body={
            "valueInputOption": "RAW",
            "data": [
                {"range": "Sheet1!K3", "values": [["FAILED"]]},
                {
                    "range": "Sheet1!M3",
                    "values": [["Gmail is not connected."]],
                },
            ],
        },
    )


def test_update_lead_email_status_returns_false_when_lead_is_missing(monkeypatch):
    _, values = _sheets_api(monkeypatch)
    values.get.return_value.execute.return_value = {"values": [["LF-OTHER"]]}

    assert sheets_service.update_lead_email_status("LF-MISSING", "SENT") is False
    values.batchUpdate.assert_not_called()


def test_update_lead_email_status_handles_sheets_api_error(monkeypatch):
    _, values = _sheets_api(monkeypatch)
    values.get.return_value.execute.return_value = {"values": [["LF-TARGET"]]}
    values.batchUpdate.return_value.execute.side_effect = HttpError(
        SimpleNamespace(status=503, reason="Service unavailable"),
        b"service unavailable",
    )

    assert (
        sheets_service.update_lead_email_status(
            "LF-TARGET",
            "SENT",
        )
        is False
    )


def test_get_lead_by_email_normalizes_match_and_pads_short_row(monkeypatch):
    _, values = _sheets_api(monkeypatch)
    values.get.return_value.execute.side_effect = [
        {"values": [["other@example.com"], ["Lead@Example.com"]]},
        {"values": [["LF-TARGET", "timestamp", "Test Lead", "Lead@Example.com"]]},
    ]

    lead = sheets_service.get_lead_by_email(" LEAD@example.com ")

    assert lead is not None
    assert lead["lead_id"] == "LF-TARGET"
    assert lead["email"] == "lead@example.com"
    assert lead["phone"] == ""
    assert values.get.call_count == 2


def test_list_leads_for_matching_reads_the_full_crm_once(monkeypatch):
    _, values = _sheets_api(monkeypatch)
    values.get.return_value.execute.return_value = {
        "values": [
            [
                "LF-1", "timestamp", "Customer", " Customer@Example.com ",
                "phone", "company", "service", "requirements", "subject",
                "response", "PENDING", "NEW", "", "budget", "TRUE",
                "SUCCESS", "summary", "next step",
            ],
            ["LF-2", "", "No email", "", "", "", "", ""],
        ]
    }

    leads = sheets_service.list_leads_for_matching()

    assert len(leads) == 2
    assert leads[0]["email"] == "customer@example.com"
    assert leads[0]["lead_id"] == "LF-1"
    assert leads[1]["email"] == ""
    values.get.assert_called_once_with(
        spreadsheetId="spreadsheet-id",
        range="Sheet1!A2:R",
    )


def test_list_leads_for_matching_handles_empty_sheet(monkeypatch):
    _, values = _sheets_api(monkeypatch)
    values.get.return_value.execute.return_value = {}

    assert sheets_service.list_leads_for_matching() == []
    values.get.assert_called_once()


def test_list_leads_for_matching_propagates_sheets_failure(monkeypatch):
    _, values = _sheets_api(monkeypatch)
    values.get.return_value.execute.side_effect = HttpError(
        SimpleNamespace(status=503, reason="Service unavailable"),
        b"service unavailable",
    )

    try:
        sheets_service.list_leads_for_matching()
    except HttpError:
        pass
    else:
        raise AssertionError("Expected Google Sheets failure to propagate")
