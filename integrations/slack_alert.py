import os
import json
import requests
from datetime import datetime


def _post(blocks: list) -> None:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("SLACK_WEBHOOK_URL is not set")
    response = requests.post(
        webhook_url,
        headers={"Content-Type": "application/json"},
        data=json.dumps({"blocks": blocks}),
        timeout=10,
    )
    response.raise_for_status()


def send_ticket_alert(ticket_id: str, issue: str, priority: str,
                      customer_name: str = "Unknown", customer_email: str = "Unknown",
                      order_number: str = "N/A") -> None:
    """Notify Slack when a new support ticket is created."""
    company = os.getenv("COMPANY_NAME", "Lumière")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    priority_emoji = {"urgent": "🔴", "high": "🟠", "normal": "🟡", "low": "🟢"}.get(priority.lower(), "⚪")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🎫 New Support Ticket — {company}"}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Ticket ID:*\n`{ticket_id}`"},
                {"type": "mrkdwn", "text": f"*Priority:*\n{priority_emoji} {priority.upper()}"},
                {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                {"type": "mrkdwn", "text": f"*Email:*\n{customer_email}"},
                {"type": "mrkdwn", "text": f"*Order No:*\n{order_number}"},
                {"type": "mrkdwn", "text": f"*Time:*\n{timestamp}"},
            ]
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Issue:*\n{issue}"}
        },
        {"type": "divider"}
    ]
    _post(blocks)


def send_purchase_alert(customer_name: str, customer_email: str,
                        product_name: str, product_price: str, product_sku: str) -> None:
    """Notify Slack when a customer expresses purchase intent."""
    company = os.getenv("COMPANY_NAME", "Lumière")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🛍️ Purchase Intent — {company}"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"A customer wants to purchase *{product_name}*. A purchase email has been sent to them."}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Customer:*\n{customer_name}"},
                {"type": "mrkdwn", "text": f"*Email:*\n{customer_email}"},
                {"type": "mrkdwn", "text": f"*Product:*\n{product_name}"},
                {"type": "mrkdwn", "text": f"*Price:*\n{product_price}"},
                {"type": "mrkdwn", "text": f"*SKU:*\n`{product_sku}`"},
                {"type": "mrkdwn", "text": f"*Time:*\n{timestamp}"},
            ]
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "✅ Purchase email sent to customer · Follow up if no order is placed within 24 hours."}
        },
        {"type": "divider"}
    ]
    _post(blocks)


def send_escalation_alert(reason: str, conversation_summary: str = "") -> None:
    """Notify Slack when a conversation is escalated to a human agent."""
    company = os.getenv("COMPANY_NAME", "Lumière")
    agent_name = os.getenv("AGENT_NAME", "Alex")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🚨 Escalation Required — {company}"}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Agent:*\n{agent_name}"},
                {"type": "mrkdwn", "text": f"*Time:*\n{timestamp}"},
            ]
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Reason:*\n{reason}"}
        },
    ]

    if conversation_summary:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Summary:*\n{conversation_summary}"}
        })

    blocks.append({"type": "divider"})
    _post(blocks)
