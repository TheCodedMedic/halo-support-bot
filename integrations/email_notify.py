import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime


def send_ticket_email(ticket_id: str, issue: str, priority: str,
                      customer_name: str = "Unknown", customer_email: str = "Unknown",
                      order_number: str = "N/A") -> None:
    """Send a ticket notification email to the business owner via Gmail SMTP."""

    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    to_email = os.getenv("BUSINESS_EMAIL")

    if not gmail_user:
        raise RuntimeError("GMAIL_USER is not set in .env")
    if not gmail_password:
        raise RuntimeError("GMAIL_APP_PASSWORD is not set in .env")
    if not to_email:
        raise RuntimeError("BUSINESS_EMAIL is not set in .env")

    company = os.getenv("COMPANY_NAME", "Lumière")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    subject = f"New Support Ticket [{ticket_id}] — {priority.upper()}"

    html_body = f"""
    <h2 style="color:#1a1a2e">New Support Ticket — {company}</h2>
    <table style="border-collapse:collapse;width:100%;max-width:560px;font-family:sans-serif;font-size:14px">
      <tr><td style="padding:8px 12px;font-weight:bold;background:#f8f8f8">Ticket ID</td><td style="padding:8px 12px">{ticket_id}</td></tr>
      <tr><td style="padding:8px 12px;font-weight:bold;background:#f8f8f8">Priority</td><td style="padding:8px 12px">{priority.upper()}</td></tr>
      <tr><td style="padding:8px 12px;font-weight:bold;background:#f8f8f8">Customer</td><td style="padding:8px 12px">{customer_name}</td></tr>
      <tr><td style="padding:8px 12px;font-weight:bold;background:#f8f8f8">Email</td><td style="padding:8px 12px">{customer_email}</td></tr>
      <tr><td style="padding:8px 12px;font-weight:bold;background:#f8f8f8">Order No.</td><td style="padding:8px 12px">{order_number}</td></tr>
      <tr><td style="padding:8px 12px;font-weight:bold;background:#f8f8f8">Timestamp</td><td style="padding:8px 12px">{timestamp}</td></tr>
      <tr><td style="padding:8px 12px;font-weight:bold;background:#f8f8f8;vertical-align:top">Issue</td>
          <td style="padding:8px 12px">{issue}</td></tr>
    </table>
    <p style="margin-top:16px;color:#999;font-size:12px">Sent by {company} AI Support</p>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{company} Support <{gmail_user}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, to_email, msg.as_string())
