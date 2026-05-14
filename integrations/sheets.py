import os
import json
from datetime import datetime

SHEET_HEADERS = [
    "Ticket ID",
    "Category",
    "Customer Name",
    "Customer Email",
    "Order Number",
    "Priority",
    "Status",
    "Issue Summary",
    "Timestamp",
    "Notes",
]


def _get_sheet():
    """Return the first worksheet of the configured Google Sheet."""
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    json_content = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT")
    if json_content:
        creds = Credentials.from_service_account_info(json.loads(json_content), scopes=scopes)
    else:
        creds_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not creds_path or not os.path.exists(creds_path):
            raise RuntimeError("No Google credentials found.")
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)

    gc = gspread.authorize(creds)
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID is not set in .env")

    spreadsheet = gc.open_by_key(sheet_id)
    worksheet = spreadsheet.sheet1

    # Always ensure headers are correct on row 1
    existing = worksheet.row_values(1)
    if existing != SHEET_HEADERS:
        worksheet.delete_rows(1)
        worksheet.insert_row(SHEET_HEADERS, 1)
        # Apply bold + background formatting to header row
        try:
            worksheet.format("A1:J1", {
                "textFormat": {"bold": True},
                "backgroundColor": {"red": 0.1, "green": 0.1, "blue": 0.18},
                "horizontalAlignment": "CENTER",
            })
            worksheet.format("A1:J1", {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}})
        except Exception:
            pass  # formatting is cosmetic, don't fail on it

    return worksheet


def log_ticket(ticket_id: str, issue: str, priority: str,
               customer_name: str = "Unknown", customer_email: str = "Unknown",
               order_number: str = "N/A", category: str = "General") -> None:
    """Append a ticket row to the Google Sheet."""
    worksheet = _get_sheet()
    row = [
        ticket_id,
        category,
        customer_name,
        customer_email,
        order_number,
        priority.upper(),
        "Open",
        issue,
        datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "",  # Notes — blank for team to fill in
    ]
    worksheet.append_row(row)


def log_purchase(ticket_id: str, customer_name: str, customer_email: str,
                 product_name: str, product_price: str, product_sku: str) -> None:
    """Log a purchase intent row to the Google Sheet."""
    worksheet = _get_sheet()
    row = [
        ticket_id,
        "Purchase Intent",
        customer_name,
        customer_email,
        "N/A",
        "NORMAL",
        "Pending Sale",
        f"Customer wants to purchase: {product_name} ({product_sku}) at {product_price}",
        datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "Purchase email sent to customer",
    ]
    worksheet.append_row(row)
