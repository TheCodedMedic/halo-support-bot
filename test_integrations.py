"""Run this locally to test all integrations. Usage: python3 test_integrations.py"""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)

TEST_TICKET_ID  = "TKT-TEST99"
TEST_ISSUE      = "Customer reported missing order — integration test"
TEST_PRIORITY   = "high"
TEST_CATEGORY   = "Order & Shipping"
TEST_NAME       = "Test Customer"
TEST_EMAIL      = os.getenv("BUSINESS_EMAIL", "test@example.com")
TEST_ORDER      = "ORD-00000"
TEST_PRODUCT    = "Lumière Vitamin C Glow Serum"
TEST_PRICE      = "$68.00"
TEST_SKU        = "LUM-VC-001"

print("=" * 60)
print("Lumière Integration Diagnostics")
print("=" * 60)

# 1. Google Sheets
print("\n[1/5] Google Sheets — log_ticket...")
try:
    from integrations.sheets import log_ticket
    log_ticket(TEST_TICKET_ID, TEST_ISSUE, TEST_PRIORITY,
               TEST_NAME, TEST_EMAIL, TEST_ORDER, TEST_CATEGORY)
    print("  PASS — row written to Google Sheet")
except Exception as e:
    print(f"  FAIL — {e}")

# 2. Owner notification email
print("\n[2/5] Email — owner ticket notification...")
try:
    from integrations.email_notify import send_ticket_email
    send_ticket_email(TEST_TICKET_ID, TEST_ISSUE, TEST_PRIORITY,
                      TEST_NAME, TEST_EMAIL, TEST_ORDER)
    print(f"  PASS — owner email sent to {TEST_EMAIL}")
except Exception as e:
    print(f"  FAIL — {e}")

# 3. Customer confirmation email
print("\n[3/5] Email — customer confirmation...")
try:
    from integrations.email_notify import send_customer_confirmation_email
    send_customer_confirmation_email(TEST_TICKET_ID, TEST_ISSUE, TEST_PRIORITY,
                                     TEST_NAME, TEST_EMAIL)
    print(f"  PASS — customer confirmation sent to {TEST_EMAIL}")
except Exception as e:
    print(f"  FAIL — {e}")

# 4. Slack — ticket alert
print("\n[4/5] Slack — ticket creation alert...")
try:
    from integrations.slack_alert import send_ticket_alert
    send_ticket_alert(TEST_TICKET_ID, TEST_ISSUE, TEST_PRIORITY,
                      TEST_NAME, TEST_EMAIL, TEST_ORDER)
    print("  PASS — ticket alert posted to Slack")
except Exception as e:
    print(f"  FAIL — {e}")

# 5. Slack — escalation alert
print("\n[5/5] Slack — escalation alert...")
try:
    from integrations.slack_alert import send_escalation_alert
    send_escalation_alert("Integration test escalation — please ignore")
    print("  PASS — escalation alert posted to Slack")
except Exception as e:
    print(f"  FAIL — {e}")

print("\n" + "=" * 60)
print("Done.")
print("=" * 60)
