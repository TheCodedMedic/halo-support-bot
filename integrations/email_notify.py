import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime


def _send(to_email: str, subject: str, html_body: str) -> None:
    """Internal helper — send an HTML email via Gmail SMTP."""
    gmail_user = os.getenv("GMAIL_USER")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    company = os.getenv("COMPANY_NAME", "Lumière")

    if not gmail_user:
        raise RuntimeError("GMAIL_USER is not set in .env")
    if not gmail_password:
        raise RuntimeError("GMAIL_APP_PASSWORD is not set in .env")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{company} Support <{gmail_user}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, to_email, msg.as_string())


def send_ticket_email(ticket_id: str, issue: str, priority: str,
                      customer_name: str = "Unknown", customer_email: str = "Unknown",
                      order_number: str = "N/A") -> None:
    """Send a ticket notification email to the business owner."""
    to_email = os.getenv("BUSINESS_EMAIL")
    if not to_email:
        raise RuntimeError("BUSINESS_EMAIL is not set in .env")

    company = os.getenv("COMPANY_NAME", "Lumière")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    priority_color = {"urgent": "#dc2626", "high": "#ea580c", "normal": "#16a34a", "low": "#6b7280"}.get(priority.lower(), "#6b7280")

    html_body = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto">
      <div style="background:#1a1a2e;padding:28px 32px;border-radius:12px 12px 0 0">
        <h1 style="color:white;font-size:20px;margin:0">{company}</h1>
        <p style="color:rgba(255,255,255,0.55);font-size:13px;margin:4px 0 0">Support Ticket Notification</p>
      </div>
      <div style="background:#f8f9fb;padding:28px 32px;border:1px solid #eee;border-top:none;border-radius:0 0 12px 12px">
        <p style="font-size:14px;color:#444;margin-bottom:20px">A new support ticket has been created.</p>
        <table style="border-collapse:collapse;width:100%;font-size:14px">
          <tr><td style="padding:10px 14px;font-weight:600;background:#fff;border:1px solid #eee;width:35%">Ticket ID</td><td style="padding:10px 14px;background:#fff;border:1px solid #eee;font-family:monospace">{ticket_id}</td></tr>
          <tr><td style="padding:10px 14px;font-weight:600;background:#f8f9fb;border:1px solid #eee">Priority</td><td style="padding:10px 14px;background:#f8f9fb;border:1px solid #eee"><span style="background:{priority_color};color:white;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600">{priority.upper()}</span></td></tr>
          <tr><td style="padding:10px 14px;font-weight:600;background:#fff;border:1px solid #eee">Customer</td><td style="padding:10px 14px;background:#fff;border:1px solid #eee">{customer_name}</td></tr>
          <tr><td style="padding:10px 14px;font-weight:600;background:#f8f9fb;border:1px solid #eee">Email</td><td style="padding:10px 14px;background:#f8f9fb;border:1px solid #eee">{customer_email}</td></tr>
          <tr><td style="padding:10px 14px;font-weight:600;background:#fff;border:1px solid #eee">Order No.</td><td style="padding:10px 14px;background:#fff;border:1px solid #eee">{order_number}</td></tr>
          <tr><td style="padding:10px 14px;font-weight:600;background:#f8f9fb;border:1px solid #eee">Timestamp</td><td style="padding:10px 14px;background:#f8f9fb;border:1px solid #eee">{timestamp}</td></tr>
          <tr><td style="padding:10px 14px;font-weight:600;background:#fff;border:1px solid #eee;vertical-align:top">Issue</td><td style="padding:10px 14px;background:#fff;border:1px solid #eee">{issue}</td></tr>
        </table>
        <p style="margin-top:20px;color:#aaa;font-size:12px;text-align:center">Sent by {company} AI Support · {timestamp}</p>
      </div>
    </div>
    """
    _send(to_email, f"New Support Ticket [{ticket_id}] — {priority.upper()}", html_body)


def send_customer_confirmation_email(ticket_id: str, issue: str, priority: str,
                                     customer_name: str, customer_email: str) -> None:
    """Send a ticket confirmation email directly to the customer."""
    company = os.getenv("COMPANY_NAME", "Lumière")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    response_time = {"urgent": "2 hours", "high": "4 hours", "normal": "24 hours", "low": "48 hours"}.get(priority.lower(), "24 hours")

    html_body = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto">
      <div style="background:#1a1a2e;padding:32px;text-align:center;border-radius:12px 12px 0 0">
        <h1 style="color:white;font-size:24px;margin:0">{company}</h1>
        <p style="color:rgba(255,255,255,0.5);font-size:13px;margin:6px 0 0">We've received your request</p>
      </div>
      <div style="background:#ffffff;padding:32px;border:1px solid #eee;border-top:none">
        <h2 style="color:#1a1a2e;font-size:18px;margin:0 0 12px">Hi {customer_name}! 👋</h2>
        <p style="color:#555;font-size:15px;line-height:1.6;margin:0 0 24px">
          Thank you for reaching out. Your support ticket has been created and our team will be in touch with you shortly.
        </p>
        <div style="background:#f8f9fb;border-left:4px solid #6366f1;border-radius:0 8px 8px 0;padding:20px 24px;margin-bottom:24px">
          <p style="font-size:11px;color:#aaa;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px">Your Ticket Details</p>
          <p style="margin:0 0 6px;font-size:14px"><strong>Ticket ID:</strong> <span style="font-family:monospace;background:#eee;padding:2px 8px;border-radius:4px">{ticket_id}</span></p>
          <p style="margin:0 0 6px;font-size:14px"><strong>Priority:</strong> {priority.upper()}</p>
          <p style="margin:0;font-size:14px"><strong>Expected response:</strong> Within {response_time}</p>
        </div>
        <div style="background:#f8f9fb;border-radius:8px;padding:16px 20px;margin-bottom:24px">
          <p style="font-size:12px;color:#888;margin:0 0 6px;text-transform:uppercase;letter-spacing:0.5px">Issue Summary</p>
          <p style="font-size:14px;color:#333;margin:0;line-height:1.6">{issue}</p>
        </div>
        <p style="font-size:14px;color:#555;line-height:1.6;margin:0 0 24px">
          We'll send all updates to <strong>{customer_email}</strong>. If you have anything to add, simply reply to this email.
        </p>
        <hr style="border:none;border-top:1px solid #eee;margin:0 0 20px"/>
        <p style="font-size:13px;color:#aaa;margin:0">Questions? Contact us at
          <a href="mailto:support@lumiereskin.com" style="color:#6366f1">support@lumiereskin.com</a>
          or call 1-800-586-4273 (Mon–Fri 9am–6pm EST)
        </p>
      </div>
      <div style="background:#f8f9fb;padding:14px 32px;text-align:center;border:1px solid #eee;border-top:none;border-radius:0 0 12px 12px">
        <p style="font-size:11px;color:#bbb;margin:0">{company} · support@lumiereskin.com · {timestamp}</p>
      </div>
    </div>
    """
    _send(customer_email, f"We've received your request — Ticket {ticket_id}", html_body)


def send_purchase_email(customer_name: str, customer_email: str,
                        product_name: str, product_price: str,
                        product_sku: str, product_description: str = "") -> None:
    """Send a purchase intent email directly to the customer."""
    company = os.getenv("COMPANY_NAME", "Lumière")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    html_body = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto">

      <!-- Header -->
      <div style="background:#1a1a2e;padding:36px 32px;text-align:center;border-radius:12px 12px 0 0">
        <h1 style="color:white;font-size:26px;margin:0;letter-spacing:-0.5px">{company}</h1>
        <p style="color:rgba(255,255,255,0.5);font-size:13px;margin:6px 0 0">Premium Skincare</p>
      </div>

      <!-- Body -->
      <div style="background:#ffffff;padding:36px 32px;border:1px solid #eee;border-top:none">
        <h2 style="color:#1a1a2e;font-size:20px;margin:0 0 8px">Hi {customer_name}! 👋</h2>
        <p style="color:#555;font-size:15px;line-height:1.6;margin:0 0 28px">
          Thank you for your interest in our products. Here's a summary of what you'd like to order — click the button below to complete your purchase.
        </p>

        <!-- Product card -->
        <div style="background:#f8f9fb;border:1px solid #eee;border-radius:12px;padding:24px;margin-bottom:28px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div>
              <p style="font-size:11px;color:#aaa;text-transform:uppercase;letter-spacing:1px;margin:0 0 6px">Your Selected Product</p>
              <h3 style="color:#1a1a2e;font-size:17px;margin:0 0 6px">{product_name}</h3>
              <p style="color:#777;font-size:13px;margin:0 0 12px">{product_description}</p>
              <p style="font-size:11px;color:#bbb;margin:0">SKU: {product_sku}</p>
            </div>
            <div style="text-align:right;flex-shrink:0;margin-left:16px">
              <p style="font-size:26px;font-weight:700;color:#1a1a2e;margin:0">{product_price}</p>
              <p style="font-size:12px;color:#aaa;margin:4px 0 0">USD</p>
            </div>
          </div>
        </div>

        <!-- CTA Button -->
        <div style="text-align:center;margin:0 0 28px">
          <a href="https://lumiereskin.com/shop"
             style="display:inline-block;background:#1a1a2e;color:white;padding:16px 44px;border-radius:32px;text-decoration:none;font-size:15px;font-weight:600;letter-spacing:-0.2px">
            Complete Your Purchase &rarr;
          </a>
        </div>

        <!-- Trust row -->
        <div style="display:flex;justify-content:center;gap:24px;margin-bottom:28px;flex-wrap:wrap">
          <span style="font-size:12px;color:#888">✅ Free returns within 30 days</span>
          <span style="font-size:12px;color:#888">🚚 Free shipping over $65</span>
          <span style="font-size:12px;color:#888">🔒 Secure checkout</span>
        </div>

        <hr style="border:none;border-top:1px solid #eee;margin:0 0 20px"/>
        <p style="font-size:13px;color:#aaa;margin:0">
          Questions? Reply to this email or contact us at
          <a href="mailto:support@lumiereskin.com" style="color:#6366f1">support@lumiereskin.com</a>
        </p>
      </div>

      <!-- Footer -->
      <div style="background:#f8f9fb;padding:16px 32px;text-align:center;border:1px solid #eee;border-top:none;border-radius:0 0 12px 12px">
        <p style="font-size:11px;color:#bbb;margin:0">{company} · Lausanne, Switzerland · {timestamp}</p>
      </div>

    </div>
    """
    _send(customer_email, f"Your {company} Order — Complete Your Purchase", html_body)
