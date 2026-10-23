import os
import secrets
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "")
STRIPE_SECRET_KEY   = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUB_KEY      = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SEC  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
BASE_URL            = os.getenv("BASE_URL", "http://localhost:8000")
SHOP_NAME           = os.getenv("SHOP_NAME", "Elite Barbers")
# No default: set ADMIN_PASSWORD in .env. If it is missing, a random value is used so the admin panel stays locked.
ADMIN_PASSWORD      = os.getenv("ADMIN_PASSWORD") or secrets.token_urlsafe(32)
N8N_WEBHOOK_BASE    = os.getenv("N8N_WEBHOOK_BASE_URL", "")

# ── Email (Gmail SMTP) ─────────────────────────────────────────────────────────
SMTP_EMAIL          = os.getenv("SMTP_EMAIL", "")          # your Gmail address
SMTP_APP_PASSWORD   = os.getenv("SMTP_APP_PASSWORD", "")   # Gmail App Password (not your real password)
OWNER_EMAIL         = os.getenv("OWNER_EMAIL", "")         # you (Kishore) — gets every notification
BARBER_EMAIL        = os.getenv("BARBER_EMAIL", "")        # the shop owner — gets booking alerts
