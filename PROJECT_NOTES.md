# Halo AI Support Bot — Full Project Documentation

**Built by:** Ufuoma Oboh  
**Date:** May 2026  
**Status:** Live on Railway  

---

## 1. What We Built

A fully functional AI-powered customer support and sales chatbot for a skincare brand (Lumière / Halo). The bot:

- Chats naturally with customers
- Creates support tickets → logged to Google Sheets, Slack, and email
- Handles purchase requests → sends purchase email, Slack alert, logs to Sheets
- Escalates frustrated customers to a human agent via Slack

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python + Flask |
| AI Model | Anthropic Claude (claude-haiku-4-5) |
| AI Pattern | Tool use / Agentic loop |
| Email | Resend API |
| Slack | Incoming Webhooks + Block Kit |
| Database | Google Sheets (via gspread) |
| Deployment | Railway |
| Server | Gunicorn (1 worker, 120s timeout) |

---

## 3. Architecture Overview

```
User message
    ↓
Flask /chat endpoint
    ↓
Anthropic Claude API (claude-haiku-4-5)
    ↓ (tool_use stop reason)
Tool dispatcher
    ├── create_ticket()      → Sheets + Owner email + Customer email + Slack
    ├── send_purchase_email() → Customer email + Slack + Sheets
    └── escalate_to_human()  → Slack
    ↓ (end_turn stop reason)
JSON response to frontend
    ↓
Chat UI (quick reply chips, markdown rendering)
```

**Key patterns used:**
- **Prompt caching** (`cache_control: ephemeral`) — system prompt cached for 5 minutes, costs 10% of normal after first call
- **History trimming** — only last 10 messages sent to API to prevent token blowup
- **Tool loop** — up to 6 iterations per message to handle multi-step tool calls
- **Session isolation** — each user gets a UUID-keyed server-side conversation history

---

## 4. Environment Variables

All set in Railway → Variables tab.

| Variable | Purpose | Example |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API access | `sk-ant-...` |
| `SECRET_KEY` | Flask session encryption | Any random string |
| `COMPANY_NAME` | Brand name shown in UI + emails | `Lumière` |
| `AGENT_NAME` | Bot name shown in UI | `Alex` |
| `ADMIN_PASSWORD` | Password for /admin panel | Your chosen password |
| `RESEND_API_KEY` | Email sending via Resend | `re_...` |
| `BUSINESS_EMAIL` | Where owner notification emails go | `you@gmail.com` |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL | `https://hooks.slack.com/...` |
| `GOOGLE_SHEET_ID` | Google Sheet to log tickets | Long alphanumeric ID from Sheet URL |
| `GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT` | Google Sheets auth (full JSON as string) | `{"type":"service_account",...}` |
| `ACTIVE_DOCUMENT` | Which KB file to use (optional) | `sample_faq.txt` |

---

## 5. File Structure

```
support-bot/
├── app.py                        # Main Flask app, tools, routes, system prompt
├── knowledge_base.py             # KB loading + active document management
├── requirements.txt              # Python dependencies
├── Procfile                      # Gunicorn startup command
├── integrations/
│   ├── email_notify.py           # Resend email (tickets, confirmations, purchases)
│   ├── slack_alert.py            # Slack Block Kit alerts (tickets, purchases, escalations)
│   └── sheets.py                 # Google Sheets logging with cached connection
├── templates/
│   ├── index.html                # Chat UI with product cards, quick reply chips
│   └── admin.html                # Admin panel (KB upload, ticket/escalation log)
├── docs/
│   └── sample_faq.txt            # 1,000+ line knowledge base (optional, not used in current mode)
└── test_integrations.py          # Manual integration test script
```

---

## 6. Tools (AI Functions)

The bot has 3 tools it can call:

### `create_ticket`
Triggered when a customer has a support issue.  
**Collects:** full name, email, order number  
**Fires:** Slack alert + owner email + customer confirmation email + Google Sheets row  
**Categories:** Order & Shipping, Returns & Refunds, Product Inquiry, Skin Concern, Account & Loyalty, Escalation, General

### `send_purchase_email`
Triggered when a customer wants to buy a product.  
**Collects:** name, email  
**Fires:** branded purchase email to customer + Slack alert + Google Sheets row  
**Does NOT** use `create_ticket` — separate flow entirely

### `escalate_to_human`
Triggered when customer is frustrated or issue can't be resolved.  
**Fires:** Slack escalation alert with reason

---

## 7. Google Sheets Schema

10 columns, auto-created on first write:

| Column | Description |
|---|---|
| Ticket ID | Unique ID (TKT-XXXXXX or PUR-XXXXXX) |
| Category | Order & Shipping, Purchase Intent, etc. |
| Customer Name | From conversation |
| Customer Email | From conversation |
| Order Number | From conversation (N/A if not relevant) |
| Priority | LOW / NORMAL / HIGH / URGENT |
| Status | Open / Pending Sale / Resolved |
| Issue Summary | Full description of the issue |
| Timestamp | UTC time of creation |
| Notes | Blank — for team to fill in manually |

---

## 8. Bugs Fixed (Chronological)

### Bug 1 — Resend free plan restriction
**Problem:** Resend free plan only sends to the account owner's email.  
**Fix:** Switched to Gmail SMTP. Later switched back to Resend after discovering Gmail SMTP is blocked on Railway.

### Bug 2 — Knowledge base lost on Railway redeploy
**Problem:** Railway's filesystem is ephemeral — `.active_doc` pointer file wiped on every redeploy.  
**Fix:** Added `ACTIVE_DOCUMENT` environment variable support in `knowledge_base.py`. Railway env vars persist across redeploys.

### Bug 3 — Bot crashing with RateLimitError (429)
**Problem:** Full 63KB knowledge base was injected into every API call = ~15,000 tokens per message. Hit Anthropic's 30,000 tokens/minute org limit within 2 messages.  
**Fix:** Removed KB from system prompt entirely. Added `RateLimitError` catch. Added prompt caching. Added history trimming to last 10 messages.

### Bug 4 — Wrong model name crash
**Problem:** Used `claude-haiku-3-5` which is not a valid Anthropic model ID.  
**Fix:** Correct model ID is `claude-haiku-4-5`.

### Bug 5 — Background threads killed by Gunicorn
**Problem:** Moved integrations to background daemon threads thinking it would speed up responses. Gunicorn's sync worker killed daemon threads before they completed — Slack, Sheets, and email all silently failed.  
**Fix:** Reverted to synchronous calls. Added 10s SMTP timeout so nothing can hang forever.

### Bug 6 — Google Sheets making 5 API calls per write
**Problem:** `_get_sheet()` was checking and rewriting headers on every single ticket/purchase write = 3-5 API round trips before even logging the row. Slow and wasteful.  
**Fix:** Cache the worksheet connection per process. Check/write headers only once per process lifetime using a module-level flag.

### Bug 7 — Gmail SMTP blocked on Railway
**Problem:** Railway blocks outbound SMTP ports (465 and 587) to prevent spam. Gmail SMTP silently failed on the live site even though it worked locally.  
**Fix:** Switched to Resend API (HTTP-based, same as Slack webhooks — never blocked).

### Bug 8 — Knowledge base returning full document on no-match
**Problem:** When `search_knowledge_base` found no keyword match, it returned the entire 63KB document as a fallback. Worst case was worse than not having RAG at all.  
**Fix:** Return a short "no match" message instead.

---

## 9. Optimizations Made

| Optimization | Impact |
|---|---|
| Removed KB from system prompt | ~88% fewer base tokens per turn |
| Switched Sonnet → Haiku | 4× cheaper per token |
| History trimmed to last 10 messages | Prevents unbounded token growth |
| Max tokens reduced to 600 | Shorter responses, faster, cheaper |
| Prompt caching (ephemeral) | Repeat calls within 5 min cost 10% of normal |
| Sheets connection cached per process | 5 API calls → 1 per write |
| SMTP timeout added (10s) | No more indefinite hangs |

**Cost estimate (after all optimizations):**
- Per conversation turn: ~$0.001–0.002
- Full 8-message conversation: ~$0.01–0.02
- $5/month ≈ 250–500 full conversations

---

## 10. RAG Discussion

**What RAG is:** Retrieval-Augmented Generation — only retrieve knowledge when needed, rather than injecting everything upfront.

**What we tried:**
1. Initially: full 63KB FAQ injected into every system prompt (expensive, caused rate limits)
2. Implemented keyword search: split doc into chunks, score by keyword hits, return top 3 relevant blocks
3. Simplified to current approach: product list hardcoded in system prompt (~200 tokens), no KB lookup needed

**Why we simplified:** For a small product catalogue (11 products), hardcoding in the prompt is more reliable than search. RAG with a vector database (Pinecone, ChromaDB) would be justified when you have hundreds of products or multiple documents.

**If you want to scale KB in future:** ChromaDB (free, runs in-process) with sentence-transformers embeddings would give semantic search. No external service needed.

---

## 11. Email Setup Notes

**Current setup:** Resend API (HTTP)  
**Free plan limit:** Can only send to your own verified email without a custom domain.  
**To send to all customers:** Verify a custom domain in Resend dashboard (free, ~10 min with DNS access).

**Previous attempts:**
- Resend (initial) → blocked by free plan
- Gmail SMTP port 465 → blocked by Railway
- Gmail SMTP port 587 (STARTTLS) → also blocked by Railway
- Resend API (current) → works ✅

---

## 12. Admin Panel

Access at `/admin`. Password set via `ADMIN_PASSWORD` env var.

Features:
- View all tickets created this session
- View all escalations this session
- Upload a new knowledge base document (.pdf or .txt)
- Load the demo FAQ

---

## 13. Testing

### Integration test (run locally):
```bash
python3 test_integrations.py
```
Tests: Google Sheets write, owner email, customer confirmation email, Slack ticket alert, Slack escalation alert.

### Quick email test:
```bash
python3 -c "
from dotenv import load_dotenv; import os; load_dotenv('.env')
from integrations.email_notify import send_purchase_email
send_purchase_email('Test', os.getenv('BUSINESS_EMAIL'), 'Vitamin C Serum', '\$68', 'LUM-VC-001', 'Test')
print('done')
"
```

### Health check:
```
GET https://your-railway-url.railway.app/health
→ {"status": "ok"}
```

---

## 14. Deployment (Railway)

1. Push to GitHub → Railway auto-deploys from `main` branch
2. Gunicorn starts via `Procfile`: `web: gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 120`
3. All secrets in Railway Variables tab (never in code)
4. No `.env` file on Railway — env vars injected by Railway at runtime

---

## 15. Limitations & Future Improvements

| Limitation | Fix |
|---|---|
| Resend free plan (own email only) | Verify custom domain in Resend dashboard |
| In-memory ticket/session storage | Add Redis or a database for persistence across restarts |
| Single Gunicorn worker | Add more workers for higher traffic (watch for Sheets connection sharing) |
| Session lost on Railway redeploy | Expected — sessions are in-memory by design |
| No human handoff UI | Build a simple agent dashboard that receives escalations |
