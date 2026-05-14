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
        "name": "search_knowledge_base",
        "description": "Search the company knowledge base, product catalogue, and FAQ. Always call this first before answering any question about products, pricing, ingredients, policies, or orders.",
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
        "description": "Create a support ticket. Only call after collecting the customer's name, email, and order number. The customer will receive a confirmation email automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue": {"type": "string", "description": "Full description of the customer's problem"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                "category": {
                    "type": "string",
                    "enum": ["Order & Shipping", "Returns & Refunds", "Product Inquiry", "Skin Concern", "Account & Loyalty", "Purchase Intent", "Escalation", "General"],
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
        "description": "Use when a customer wants to purchase a specific product. Collect their name and email first, then call this to send them a purchase email and notify the team. Do NOT use create_ticket for purchases — use this instead.",
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
        "description": "Escalate to a human agent immediately. Use when the customer is frustrated, upset, or when two knowledge base searches have not resolved the issue.",
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

def search_knowledge_base(query: str) -> str:
    _, content = get_active_document()
    if not content:
        return "No knowledge base loaded."
    query_lower = query.lower()
    lines = [l for l in content.splitlines() if query_lower in l.lower()]
    if lines:
        return "\n".join(lines)
    return content


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
    # Google Sheets
    try:
        from integrations.sheets import log_ticket
        log_ticket(ticket_id, issue, priority, customer_name, customer_email, order_number, category)
    except Exception as e:
        print(f"[sheets] {e}")
    # Email → business owner
    try:
        from integrations.email_notify import send_ticket_email
        send_ticket_email(ticket_id, issue, priority, customer_name, customer_email, order_number)
    except Exception as e:
        print(f"[email-owner] {e}")
    # Email → customer confirmation
    try:
        from integrations.email_notify import send_customer_confirmation_email
        send_customer_confirmation_email(ticket_id, issue, priority, customer_name, customer_email)
    except Exception as e:
        print(f"[email-customer] {e}")
    # Slack
    try:
        from integrations.slack_alert import send_ticket_alert
        send_ticket_alert(ticket_id, issue, priority, customer_name, customer_email, order_number)
    except Exception as e:
        print(f"[slack-ticket] {e}")
    return f"Ticket {ticket_id} created successfully. A confirmation email has been sent to {customer_email}. Our team will respond within 24 hours."


def send_purchase_email(customer_name: str, customer_email: str, product_name: str,
                        product_price: str, product_sku: str, product_description: str = "") -> str:
    ref_id = f"PUR-{str(uuid.uuid4())[:6].upper()}"
    # Email → customer
    try:
        from integrations.email_notify import send_purchase_email as _send_purchase
        _send_purchase(customer_name, customer_email, product_name, product_price, product_sku, product_description)
    except Exception as e:
        print(f"[email-purchase] {e}")
    # Slack
    try:
        from integrations.slack_alert import send_purchase_alert
        send_purchase_alert(customer_name, customer_email, product_name, product_price, product_sku)
    except Exception as e:
        print(f"[slack-purchase] {e}")
    # Sheets
    try:
        from integrations.sheets import log_purchase
        log_purchase(ref_id, customer_name, customer_email, product_name, product_price, product_sku)
    except Exception as e:
        print(f"[sheets-purchase] {e}")
    return f"A purchase email has been sent to {customer_email} with a link to complete their order for {product_name}. Reference: {ref_id}."


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
    return "I'm connecting you with a human agent right now. Average wait time is under 3 minutes. They will have the full context of our conversation."


TOOL_MAP = {
    "search_knowledge_base": search_knowledge_base,
    "create_ticket": create_ticket,
    "send_purchase_email": send_purchase_email,
    "escalate_to_human": escalate_to_human,
}

# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────

SYSTEM_BASE = """\
You are {agent_name}, a warm, knowledgeable customer support and sales specialist for {company_name}, a premium skincare brand.

PERSONALITY: Polished, empathetic, and confident. You represent a luxury brand — be warm but professional. You are also a product expert who genuinely loves skincare and can make great recommendations.

PROCESS:
1. Greet the customer and understand their need
2. Always search the knowledge base before answering ANY question (products, prices, ingredients, policies, routines)
3. For support issues: answer clearly and ask if it resolved their concern. If not, collect name + email + order number then create_ticket.
4. For product questions: recommend confidently based on skin type, concern, and budget. If they want to buy, collect name + email then use send_purchase_email.
5. If the customer is frustrated or upset → escalate_to_human immediately.

TICKET RULES:
- Never call create_ticket until you have: full name, email, and order number (or confirmed N/A)
- Always read back their details before submitting and ask "Does everything look correct?"
- After ticket is created, tell them they'll receive a confirmation email

PURCHASE RULES:
- When a customer wants to buy a product, ask for their name and email only (no order number needed)
- Use send_purchase_email — NOT create_ticket — for purchases
- Confirm what they're buying and the price before sending

PRODUCT EXPERTISE:
- You know every product in the catalogue including SKU, price, ingredients, and skin type suitability
- Make confident recommendations based on skin type and concerns
- Suggest complementary products and routines
- Mention current bundles if relevant

PRODUCT DISPLAY FORMAT:
NEVER use markdown tables to display products — they break in chat interfaces.
Instead, display each product as a card block using this EXACT format:

[PRODUCT]
name: Product Name
price: $XX.00
sku: LUM-XX-000
tag: Best for oily skin · Anti-ageing
desc: One sentence about what it does.
[/PRODUCT]

Show up to 4 products maximum per response. After the product cards, add a short
1–2 sentence follow-up (e.g. routine suggestion, bundle mention, or offer to help buy).

QUICK REPLY SUGGESTIONS:
After each response (except while collecting customer details), add a line:
QUICK_REPLIES: Short option | Short option | Short option
Keep each under 32 characters. Match them to the topic just discussed.
Examples by topic:
- Shipping: QUICK_REPLIES: Track my order | Express shipping | Free shipping info
- Returns: QUICK_REPLIES: Start a return | Refund timeline | Exchange an item
- Product advice: QUICK_REPLIES: View full routine | Check ingredients | I'd like to buy this
- After ticket: QUICK_REPLIES: Ask another question | Track my order | Speak to a human
- After purchase email: QUICK_REPLIES: Ask about ingredients | Build my routine | More products"""


def build_system_prompt() -> str:
    agent_name = os.getenv("AGENT_NAME", "Alex")
    company_name = os.getenv("COMPANY_NAME", "Lumière")
    return SYSTEM_BASE.format(agent_name=agent_name, company_name=company_name)

# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/")
def index():
    # Reuse existing session if valid, create new one otherwise
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

        # Keep only the last 10 messages to prevent token blowup
        trimmed = history[-10:] if len(history) > 10 else history

        for _ in range(8):
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
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
                            print(f"[chat] unknown tool requested: {block.name}")
                            result = f"Tool '{block.name}' is not available."
                        else:
                            try:
                                result = tool_fn(**block.input)
                            except Exception as tool_err:
                                print(f"[chat] tool '{block.name}' raised: {tool_err}")
                                result = f"There was an issue running {block.name}. Please continue."
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })
                history.append({"role": "user", "content": tool_results})

        return jsonify({"reply": "I'm having a little trouble right now. Please try again or contact us at support@lumiereskin.com.", "suggestions": []})

    except anthropic.RateLimitError:
        print("[chat] rate limit hit — too many tokens per minute")
        return jsonify({"reply": "I'm receiving a lot of messages right now — please give me a moment and try again.", "suggestions": []}), 200
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
