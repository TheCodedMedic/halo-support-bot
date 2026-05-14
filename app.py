from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from dotenv import load_dotenv
from knowledge_base import get_active_document, load_document, set_active_document, DOCS_DIR
from werkzeug.utils import secure_filename
import anthropic
import os
import uuid

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_env_path, override=True)

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
        "description": "Create a support ticket. Only call this after you have collected the customer's name, email, and order number (if relevant). Never call this before asking for those details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue": {"type": "string", "description": "Full description of the customer's problem"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                "customer_name": {"type": "string"},
                "customer_email": {"type": "string"},
                "order_number": {"type": "string", "description": "Order number if relevant, otherwise 'N/A'"}
            },
            "required": ["issue", "priority", "customer_name", "customer_email", "order_number"]
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

def create_ticket(issue: str, priority: str = "normal", customer_name: str = "Unknown",
                  customer_email: str = "Unknown", order_number: str = "N/A") -> str:
    from datetime import datetime
    ticket_id = f"TKT-{str(uuid.uuid4())[:6].upper()}"
    ticket_log.append({
        "ticket_id": ticket_id,
        "issue": issue,
        "priority": priority,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "order_number": order_number,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    })
    try:
        from integrations.sheets import log_ticket
        log_ticket(ticket_id, issue, priority, customer_name, customer_email, order_number)
    except Exception as e:
        print(f"[sheets] failed to log ticket: {e}")
    try:
        from integrations.email_notify import send_ticket_email
        send_ticket_email(ticket_id, issue, priority, customer_name, customer_email, order_number)
    except Exception as e:
        print(f"[email] failed to send notification: {e}")
    return f"Ticket {ticket_id} created with {priority} priority. Our team will be in touch at {customer_email} within 24 hours."

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
You are {agent_name}, a warm and knowledgeable customer support specialist for {company_name}, a premium skincare brand.

PERSONALITY: Polished, empathetic, and efficient. You represent a luxury brand — be warm but professional. Never rushed.

PROCESS:
1. Greet the customer and understand their issue
2. Search the knowledge base before answering anything
3. If the FAQ answers it → give a clear, friendly answer and ask if it helped
4. If the issue needs follow-up (no FAQ answer, complex issue, or customer requests it):
   a. Tell the customer you'll create a ticket for them
   b. Ask for their full name, email address, and order number (say "N/A" if not order-related)
   c. Only call create_ticket once you have all three
5. If the customer is frustrated or upset → escalate to a human immediately, do not wait

RULES:
- Never make up product information — always search first
- Keep replies concise — 2-4 sentences unless explaining a complex issue
- Always confirm the customer's email back to them before submitting a ticket
- Use the customer's name once you have it
- Never ask for payment details or passwords

QUICK REPLY SUGGESTIONS:
After answering a question (not while collecting name/email/order number), add a final line with 2–4 short clickable options:
QUICK_REPLIES: Option one | Option two | Option three
Keep each option under 32 characters. Make them specific to what the customer just asked about.
Examples:
- After a shipping question: QUICK_REPLIES: Track my order | Shipping costs | International shipping
- After a returns question: QUICK_REPLIES: Start a return | Refund timeline | Exchange an item
- After a product question: QUICK_REPLIES: Full ingredients list | Recommended routine | Order now
- After greeting/intro: QUICK_REPLIES: Track my order | Return a product | Product advice | Speak to a human
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

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


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
            # Parse and strip QUICK_REPLIES from the reply
            suggestions = []
            clean_lines = []
            for line in reply.splitlines():
                if line.strip().startswith("QUICK_REPLIES:"):
                    raw = line.replace("QUICK_REPLIES:", "").strip()
                    suggestions = [s.strip() for s in raw.split("|") if s.strip()]
                else:
                    clean_lines.append(line)
            clean_reply = "\n".join(clean_lines).strip()
            return jsonify({"reply": clean_reply, "suggestions": suggestions})

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
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)