import os
import json
from datetime import datetime

SHEET_HEADERS = ["Ticket ID", "Customer Message", "Priority", "Status", "Timestamp"]


def _get_sheet():
    """Return the first worksheet of the configured Google Sheet."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    # Prefer inline JSON content (Railway/cloud) over file path (local dev)
    json_content = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT")
    if json_content:
        creds = Credentials.from_service_account_info(json.loads(json_content), scopes=scopes)
    else:
        creds_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not creds_path or not os.path.exists(creds_path):
            raise RuntimeError("No Google credentials found. Set GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT or GOOGLE_SERVICE_ACCOUNT_JSON.")
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    gc = gspread.authorize(creds)
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID is not set in .env")

    spreadsheet = gc.open_by_key(sheet_id)
    worksheet = spreadsheet.sheet1

    # Write headers if the sheet is empty
    if not worksheet.row_values(1):
        worksheet.append_row(SHEET_HEADERS)

    return worksheet


def log_ticket(ticket_id: str, customer_message: str, priority: str) -> None:
    """Append a ticket row to the Google Sheet. Raises on failure."""
    worksheet = _get_sheet()
    row = [
        ticket_id,
        customer_message,
        priority,
        "Open",
        datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    ]
    worksheet.append_row(row)
