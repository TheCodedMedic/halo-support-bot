import os
from datetime import datetime


def send_ticket_email(ticket_id: str, customer_message: str, priority: str) -> None:
    """Send a ticket notification email to the business owner via Resend."""
    import resend

    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not set in .env")

    to_email = os.getenv("BUSINESS_EMAIL")
    if not to_email:
        raise RuntimeError("BUSINESS_EMAIL is not set in .env")

    company = os.getenv("COMPANY_NAME", "SupportAI")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    resend.api_key = api_key
    resend.Emails.send({
        "from": f"{company} Support <onboarding@resend.dev>",
        "to": [to_email],
        "subject": f"New Support Ticket [{ticket_id}] — {priority.upper()}",
        "html": f"""
        <h2>New Support Ticket</h2>
        <table style="border-collapse:collapse;width:100%;max-width:500px">
          <tr><td style="padding:8px;font-weight:bold">Ticket ID</td><td style="padding:8px">{ticket_id}</td></tr>
          <tr><td style="padding:8px;font-weight:bold">Priority</td><td style="padding:8px">{priority.upper()}</td></tr>
          <tr><td style="padding:8px;font-weight:bold">Timestamp</td><td style="padding:8px">{timestamp}</td></tr>
          <tr><td style="padding:8px;font-weight:bold;vertical-align:top">Customer Message</td>
              <td style="padding:8px">{customer_message}</td></tr>
        </table>
        <p style="margin-top:16px;color:#666">Sent by {company} SupportAI</p>
        """,
    })
