import os
import json
import requests
from datetime import datetime


def send_escalation_alert(reason: str, conversation_summary: str = "") -> None:
    """POST an escalation alert to the configured Slack Incoming Webhook."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("SLACK_WEBHOOK_URL is not set in .env")

    company = os.getenv("COMPANY_NAME", "SupportAI")
    agent_name = os.getenv("AGENT_NAME", "Alex")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f":rotating_light: Escalation Required — {company}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Agent:*\n{agent_name}"},
                {"type": "mrkdwn", "text": f"*Time:*\n{timestamp}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Reason:*\n{reason}"},
        },
    ]

    if conversation_summary:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Conversation summary:*\n{conversation_summary}"},
        })

    blocks.append({"type": "divider"})

    response = requests.post(
        webhook_url,
        headers={"Content-Type": "application/json"},
        data=json.dumps({"blocks": blocks}),
        timeout=10,
    )
    response.raise_for_status()
