from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from dotenv import load_dotenv
from knowledge_base import get_active_document, load_document, set_active_document, DOCS_DIR
from werkzeug.utils import secure_filename
import anthropic
import os
import uuid

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24).hex())
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

conversations = {}  # session_id -> list of messages

TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": "Search the company FAQ and knowledge base. Always use this first before answering any support question.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_ticket",
        "description": "Create a support ticket for issues that need follow-up. Use when the knowledge base has no answer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue": {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]}
            },
            "required": ["issue", "priority"]
        }
    },
    {
        "name": "escalate_to_human",
        "description": "Escalate to a human agent. Use when customer is frustrated or 2 searches failed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"}
            },
            "required": ["reason"]
        }
    }
]

def search_knowledge_base(query: str) -> str:
    _, content = get_active_document()
    if not content:
        return "No knowledge base loaded. Please contact support directly."
    query_lower = query.lower()
    lines = [l for l in content.splitlines() if query_lower in l.lower()]
    if lines:
        return "\n".join(lines)
    # Fall back to returning the full document so the agent can scan it
    return content

def create_ticket(issue: str, priority: str = "normal") -> str:
    from datetime import datetime
    ticket_id = f"TKT-{str(uuid.uuid4())[:6].upper()}"
    ticket_log.append({
        "ticket_id": ticket_id,
        "issue": issue,
        "priority": priority,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    })
    try:
        from integrations.sheets import log_ticket
        log_ticket(ticket_id, issue, priority)
    except Exception as e:
        print(f"[sheets] failed to log ticket: {e}")
    try:
        from integrations.email_notify import send_ticket_email
        send_ticket_email(ticket_id, issue, priority)
    except Exception as e:
        print(f"[email] failed to send notification: {e}")
    return f"Ticket {ticket_id} created with {priority} priority. Our team will respond within 24 hours."

def escalate_to_human(reason: str) -> str:
    from datetime import datetime
    escalation_log.append({
        "reason": reason,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    })
    try:
        from integrations.slack_alert import send_escalation_alert
        send_escalation_alert(reason)
    except Exception as e:
        print(f"[slack] failed to send escalation: {e}")
    return "Connecting you to a human agent now. Average wait time is 3 minutes."

TOOL_MAP = {
    "search_knowledge_base": search_knowledge_base,
    "create_ticket": create_ticket,
    "escalate_to_human": escalate_to_human
}

SYSTEM_BASE = """\
You are {agent_name}, a friendly customer support agent for {company_name}.

PERSONALITY: Warm, helpful, and concise. Get to the answer quickly.

PROCESS:
1. Understand the customer's issue
2. Search the knowledge base first
3. If found → give the answer and ask if resolved
4. If not found → create a ticket
5. If customer seems frustrated → escalate immediately

RULES:
- Never make up information
- Keep replies short — 2-3 sentences max
- Always search before saying you don't know
{kb_section}"""


def build_system_prompt() -> str:
    agent_name = os.getenv("AGENT_NAME", "Alex")
    company_name = os.getenv("COMPANY_NAME", "SupportAI")
    _, kb_content = get_active_document()
    if kb_content:
        kb_section = f"\nKNOWLEDGE BASE:\n{kb_content}"
    else:
        kb_section = "\nNo knowledge base is loaded. Use the search tool and rely on general support best practices."
    return SYSTEM_BASE.format(agent_name=agent_name, company_name=company_name, kb_section=kb_section)

@app.route("/")
def index():
    sid = str(uuid.uuid4())
    session["id"] = sid
    conversations[sid] = []
    return render_template(
        "index.html",
        company_name=os.getenv("COMPANY_NAME", "SupportAI"),
        agent_name=os.getenv("AGENT_NAME", "Alex"),
    )

@app.route("/chat", methods=["POST"])
def chat():
    sid = session.get("id")
    if not sid or sid not in conversations:
        sid = str(uuid.uuid4())
        session["id"] = sid
        conversations[sid] = []
    history = conversations[sid]

    user_message = request.json.get("message", "")
    history.append({"role": "user", "content": user_message})

    for _ in range(6):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=build_system_prompt(),
            tools=TOOLS,
            messages=history
        )

        if response.stop_reason == "end_turn":
            reply = next(b.text for b in response.content if hasattr(b, "text"))
            history.append({"role": "assistant", "content": reply})
            return jsonify({"reply": reply})

        if response.stop_reason == "tool_use":
            history.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = TOOL_MAP[block.name](**block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            history.append({"role": "user", "content": tool_results})

    return jsonify({"reply": "I'm having trouble right now. Please try again."})

ticket_log = []  # list of dicts: {ticket_id, issue, priority, timestamp}
escalation_log = []  # list of dicts: {reason, timestamp}


def _admin_authed() -> bool:
    return session.get("admin") is True


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST" and not _admin_authed():
        password = request.form.get("password", "")
        if password == os.getenv("ADMIN_PASSWORD", "admin"):
            session["admin"] = True
        else:
            flash("Incorrect password.")
        return redirect(url_for("admin"))

    if not _admin_authed():
        return render_template("admin.html", authenticated=False)

    filename, kb_content = get_active_document()
    return render_template(
        "admin.html",
        authenticated=True,
        ticket_log=ticket_log,
        escalation_log=escalation_log,
        kb_filename=filename,
        kb_preview=kb_content[:500] if kb_content else None,
        company_name=os.getenv("COMPANY_NAME", "SupportAI"),
    )


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin"))


@app.route("/admin/upload", methods=["POST"])
def admin_upload():
    if not _admin_authed():
        return redirect(url_for("admin"))
    file = request.files.get("document")
    if not file or file.filename == "":
        flash("No file selected.")
        return redirect(url_for("admin"))
    filename = secure_filename(file.filename)
    if not filename.lower().endswith((".pdf", ".txt")):
        flash("Only .pdf and .txt files are supported.")
        return redirect(url_for("admin"))
    save_path = os.path.join(DOCS_DIR, filename)
    file.save(save_path)
    try:
        load_document(save_path)  # validate it parses correctly
        set_active_document(filename)
        flash(f"Knowledge base updated: {filename}")
    except Exception as e:
        os.remove(save_path)
        flash(f"Failed to load document: {e}")
    return redirect(url_for("admin"))


@app.route("/admin/load-demo", methods=["POST"])
def admin_load_demo():
    if not _admin_authed():
        return redirect(url_for("admin"))
    demo_path = os.path.join(DOCS_DIR, "sample_faq.txt")
    if not os.path.exists(demo_path):
        flash("Demo FAQ file not found.")
        return redirect(url_for("admin"))
    set_active_document("sample_faq.txt")
    flash("Demo FAQ loaded successfully.")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)