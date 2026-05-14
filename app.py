from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from dotenv import load_dotenv
from knowledge_base import get_active_document, load_document, set_active_document, DOCS_DIR
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import anthropic
import os
import uuid

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_env_path, override=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24).hex())
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=24)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

conversations = {}  # session_id -> list of messages
ticket_log = []
escalation_log = []

# ─────────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────────

TOOLS = [
    {
        "name": "create_ticket",
        "description": "Create a support ticket. Only call after collecting the customer's name, email, and order number. Fires a Slack alert, emails the business owner, and sends the customer a confirmation email automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue": {"type": "string", "description": "Full description of the customer's problem"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                "category": {
                    "type": "string",
                    "enum": ["Order & Shipping", "Returns & Refunds", "Product Inquiry",
                             "Skin Concern", "Account & Loyalty", "Purchase Intent",
                             "Escalation", "General"],
                    "description": "Category that best describes the issue"
                },
                "customer_name": {"type": "string"},
                "customer_email": {"type": "string"},
                "order_number": {"type": "string", "description": "Order number if relevant, otherwise 'N/A'"}
            },
            "required": ["issue", "priority", "category", "customer_name", "customer_email", "order_number"]
        }
    },
    {
        "name": "send_purchase_email",
        "description": "Send a purchase email to a customer who wants to buy a product. Collect their name and email first, then call this. Do NOT use create_ticket for purchases.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string"},
                "customer_email": {"type": "string"},
                "product_name": {"type": "string"},
                "product_price": {"type": "string", "description": "e.g. '$68.00'"},
                "product_sku": {"type": "string"},
                "product_description": {"type": "string", "description": "One-line product description"}
            },
            "required": ["customer_name", "customer_email", "product_name", "product_price", "product_sku", "product_description"]
        }
    },
    {
        "name": "escalate_to_human",
        "description": "Escalate to a human agent. Use when the customer is frustrated, upset, or you cannot resolve the issue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"}
            },
            "required": ["reason"]
        }
    }
]

# ─────────────────────────────────────────────
# TOOL IMPLEMENTATIONS
# ─────────────────────────────────────────────

def create_ticket(issue: str, priority: str = "normal", category: str = "General",
                  customer_name: str = "Unknown", customer_email: str = "Unknown",
                  order_number: str = "N/A") -> str:
    ticket_id = f"TKT-{str(uuid.uuid4())[:6].upper()}"
    ticket_log.append({
        "ticket_id": ticket_id,
        "issue": issue,
        "priority": priority,
        "category": category,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "order_number": order_number,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    })
    try:
        from integrations.sheets import log_ticket
        log_ticket(ticket_id, issue, priority, customer_name, customer_email, order_number, category)
    except Exception as e:
        print(f"[sheets] {e}")
    try:
        from integrations.email_notify import send_ticket_email
        send_ticket_email(ticket_id, issue, priority, customer_name, customer_email, order_number)
    except Exception as e:
        print(f"[email-owner] {e}")
    try:
        from integrations.email_notify import send_customer_confirmation_email
        send_customer_confirmation_email(ticket_id, issue, priority, customer_name, customer_email)
    except Exception as e:
        print(f"[email-customer] {e}")
    try:
        from integrations.slack_alert import send_ticket_alert
        send_ticket_alert(ticket_id, issue, priority, customer_name, customer_email, order_number)
    except Exception as e:
        print(f"[slack-ticket] {e}")
    return f"Ticket {ticket_id} created. Confirmation email sent to {customer_email}. Our team will respond within 24 hours."


def send_purchase_email(customer_name: str, customer_email: str, product_name: str,
                        product_price: str, product_sku: str, product_description: str = "") -> str:
    ref_id = f"PUR-{str(uuid.uuid4())[:6].upper()}"
    try:
        from integrations.email_notify import send_purchase_email as _send_purchase
        _send_purchase(customer_name, customer_email, product_name, product_price, product_sku, product_description)
    except Exception as e:
        print(f"[email-purchase] {e}")
    try:
        from integrations.slack_alert import send_purchase_alert
        send_purchase_alert(customer_name, customer_email, product_name, product_price, product_sku)
    except Exception as e:
        print(f"[slack-purchase] {e}")
    try:
        from integrations.sheets import log_purchase
        log_purchase(ref_id, customer_name, customer_email, product_name, product_price, product_sku)
    except Exception as e:
        print(f"[sheets-purchase] {e}")
    return f"Purchase email sent to {customer_email} for {product_name}. Reference: {ref_id}."


def escalate_to_human(reason: str) -> str:
    escalation_log.append({
        "reason": reason,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    })
    try:
        from integrations.slack_alert import send_escalation_alert
        send_escalation_alert(reason)
    except Exception as e:
        print(f"[slack-escalation] {e}")
    return "I'm connecting you with a human agent right now. They will have the full context of our conversation."


TOOL_MAP = {
    "create_ticket": create_ticket,
    "send_purchase_email": send_purchase_email,
    "escalate_to_human": escalate_to_human,
}

# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────

SYSTEM = """\
You are {agent_name}, a friendly and professional customer support agent for {company_name}, a premium skincare brand.

YOUR JOB:
1. Chat warmly and helpfully with customers
2. For any support issue → collect name, email, order number → create_ticket
3. For purchase requests → collect name and email → send_purchase_email
4. If the customer is upset or you can't help → escalate_to_human

TICKET FLOW:
- Understand the problem first
- Ask for: full name, email address, order number (say N/A if no order)
- Read back their details: "Just to confirm — Name: X, Email: Y, Order: Z. Is that correct?"
- Only call create_ticket after they confirm
- Tell them a confirmation email has been sent

PURCHASE FLOW:
- Ask what product they want to buy
- Ask for their name and email
- Confirm: "I'll send a purchase email for [product] at [price] to [email]. Does that look right?"
- Call send_purchase_email — NOT create_ticket

OUR PRODUCTS:
- Vitamin C Glow Serum — $68 (SKU: LUM-VC-001) — brightens skin, fades dark spots
- Retinol Night Cream — $78 (SKU: LUM-RT-002) — anti-ageing, reduces fine lines
- Hydra-Calm Cleanser — $38 (SKU: LUM-HC-003) — gentle daily cleanser, all skin types
- Moisture Surge Moisturiser — $58 (SKU: LUM-MS-004) — 72-hour hydration
- SPF 50 Glow Shield — $45 (SKU: LUM-SP-005) — broad spectrum SPF50
- Renewal Eye Cream — $65 (SKU: LUM-EC-006) — reduces dark circles and puffiness
- Royal Honey Mask — $52 (SKU: LUM-RH-007) — deep nourishing weekly mask
- AHA Resurfacing Toner — $42 (SKU: LUM-AH-008) — exfoliates, smooths texture
- Bakuchiol Balancing Serum — $72 (SKU: LUM-BB-009) — natural retinol alternative, sensitive skin
- Ceramide Barrier Cream — $55 (SKU: LUM-CB-010) — repairs and strengthens skin barrier
- Niacinamide Clarity Serum — $48 (SKU: LUM-NI-011) — minimises pores, controls oil, oily/acne skin

QUICK REPLIES:
After every response add one line: QUICK_REPLIES: Option 1 | Option 2 | Option 3
Keep each option under 32 characters. Match to the current topic.
Examples:
- General: QUICK_REPLIES: I have an issue | I want to buy | Speak to a human
- After ticket: QUICK_REPLIES: Ask another question | Speak to a human | Track my order
- After purchase: QUICK_REPLIES: Buy another product | I have a question | Thank you
- Browsing products: QUICK_REPLIES: I'd like to buy this | Tell me more | See other products"""


def build_system_prompt() -> str:
    agent_name = os.getenv("AGENT_NAME", "Alex")
    company_name = os.getenv("COMPANY_NAME", "Lumière")
    return SYSTEM.format(agent_name=agent_name, company_name=company_name)


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/")
def index():
    sid = session.get("id")
    if not sid or sid not in conversations:
        sid = str(uuid.uuid4())
        session["id"] = sid
        session.permanent = True
        conversations[sid] = []
    return render_template(
        "index.html",
        company_name=os.getenv("COMPANY_NAME", "Lumière"),
        agent_name=os.getenv("AGENT_NAME", "Alex"),
    )


@app.route("/chat", methods=["POST"])
def chat():
    try:
        sid = session.get("id")
        if not sid or sid not in conversations:
            sid = str(uuid.uuid4())
            session["id"] = sid
            session.permanent = True
            conversations[sid] = []
        history = conversations[sid]

        user_message = request.json.get("message", "")
        if not user_message:
            return jsonify({"reply": "I didn't catch that — could you try again?", "suggestions": []})

        history.append({"role": "user", "content": user_message})

        # Keep only the last 10 messages to stay within token limits
        trimmed = history[-10:] if len(history) > 10 else history

        for _ in range(6):
            response = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=600,
                system=[{
                    "type": "text",
                    "text": build_system_prompt(),
                    "cache_control": {"type": "ephemeral"}
                }],
                tools=TOOLS,
                messages=trimmed
            )

            if response.stop_reason == "end_turn":
                reply = next((b.text for b in response.content if hasattr(b, "text")), "")
                history.append({"role": "assistant", "content": reply})
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
                        tool_fn = TOOL_MAP.get(block.name)
                        if tool_fn is None:
                            result = f"Tool '{block.name}' is not available."
                        else:
                            try:
                                result = tool_fn(**block.input)
                            except Exception as tool_err:
                                print(f"[chat] tool '{block.name}' raised: {tool_err}")
                                result = f"There was an issue running {block.name}. Please try again."
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })
                history.append({"role": "user", "content": tool_results})

        return jsonify({"reply": "I'm having a little trouble right now. Please try again in a moment.", "suggestions": []})

    except anthropic.RateLimitError:
        print("[chat] rate limit hit")
        return jsonify({"reply": "I'm very busy right now — please give me a moment and try again.", "suggestions": []}), 200
    except Exception as e:
        print(f"[chat] unhandled error: {e}")
        import traceback; traceback.print_exc()
        return jsonify({"reply": "Something went wrong on my end. Please try again in a moment.", "suggestions": []}), 200


# ─────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────

def _admin_authed() -> bool:
    return session.get("admin") is True


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST" and not _admin_authed():
        password = request.form.get("password", "")
        if password == os.getenv("ADMIN_PASSWORD", "admin"):
            session["admin"] = True
            session.permanent = True
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
        company_name=os.getenv("COMPANY_NAME", "Lumière"),
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
        load_document(save_path)
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
