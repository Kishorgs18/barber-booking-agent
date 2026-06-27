"""
Email notifications and calendar helpers.
All sends are fire-and-forget (background thread) — never blocks the API.
"""
import smtplib
import threading
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlencode

from config import SMTP_EMAIL, SMTP_APP_PASSWORD, OWNER_EMAIL, BARBER_EMAIL, SHOP_NAME, BASE_URL


# ── Core sender ────────────────────────────────────────────────────────────────

def _send(recipients: list[str], subject: str, html: str):
    targets = [e for e in recipients if e and "@" in e]
    if not targets or not SMTP_EMAIL or not SMTP_APP_PASSWORD:
        return

    def _worker():
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"]  = subject
            msg["From"]     = f"{SHOP_NAME} Bookings <{SMTP_EMAIL}>"
            msg["To"]       = ", ".join(targets)
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as srv:
                srv.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
                srv.sendmail(SMTP_EMAIL, targets, msg.as_string())
            print(f"[email] sent '{subject}' → {targets}")
        except Exception as exc:
            print(f"[email] FAILED: {exc}")

    threading.Thread(target=_worker, daemon=True).start()


# ── Calendar helpers ───────────────────────────────────────────────────────────

def google_calendar_url(booking: dict) -> str:
    start = datetime.strptime(
        f"{booking['booking_date']} {booking['booking_time']}", "%Y-%m-%d %H:%M"
    )
    end = start + timedelta(minutes=int(booking.get("duration_minutes", 30)))
    params = {
        "action":  "TEMPLATE",
        "text":    f"{booking['service_name']} — {SHOP_NAME}",
        "dates":   f"{start.strftime('%Y%m%dT%H%M%S')}/{end.strftime('%Y%m%dT%H%M%S')}",
        "details": f"Booking #{booking['id']}\nCustomer: {booking.get('customer_name','')}\nPhone: {booking.get('customer_phone','')}",
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def ics_content(booking: dict) -> str:
    start = datetime.strptime(
        f"{booking['booking_date']} {booking['booking_time']}", "%Y-%m-%d %H:%M"
    )
    end = start + timedelta(minutes=int(booking.get("duration_minutes", 30)))
    return "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{SHOP_NAME}//Booking//EN",
        "BEGIN:VEVENT",
        f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{booking['service_name']} — {SHOP_NAME}",
        f"DESCRIPTION:Booking #{booking['id']} | {booking.get('customer_name','')} | {booking.get('customer_phone','')}",
        f"LOCATION:{SHOP_NAME}",
        "END:VEVENT",
        "END:VCALENDAR",
    ])


# ── Notification functions ─────────────────────────────────────────────────────

def notify_new_booking(booking: dict):
    """Email to owner + barber when a booking is created (awaiting payment)."""
    gcal = google_calendar_url(booking)
    ics_url = f"{BASE_URL}/api/booking/{booking['id']}/calendar.ics"
    subject = f"✂️ New Booking — {booking['customer_name']} on {booking['booking_date']}"
    _send(
        [OWNER_EMAIL, BARBER_EMAIL],
        subject,
        _owner_new_booking_html(booking, gcal, ics_url),
    )


def notify_payment_confirmed(booking: dict):
    """
    Email to owner + barber: payment received.
    Email to customer: confirmation + calendar link (if email provided).
    """
    gcal = google_calendar_url(booking)
    ics_url = f"{BASE_URL}/api/booking/{booking['id']}/calendar.ics"

    # Owner / barber
    subject_owner = f"💰 Paid — {booking['customer_name']} — £{booking['price_gbp']}"
    _send(
        [OWNER_EMAIL, BARBER_EMAIL],
        subject_owner,
        _owner_payment_html(booking, gcal, ics_url),
    )

    # Customer (only if they gave an email)
    if booking.get("customer_email"):
        subject_customer = f"✅ Appointment confirmed at {SHOP_NAME}!"
        _send(
            [booking["customer_email"]],
            subject_customer,
            _customer_confirmed_html(booking, gcal, ics_url),
        )


def notify_cancellation(booking: dict):
    """Email to owner + barber when a booking is cancelled."""
    subject = f"❌ Cancelled — {booking['customer_name']} on {booking['booking_date']}"
    _send(
        [OWNER_EMAIL, BARBER_EMAIL],
        subject,
        _cancellation_html(booking),
    )


# ── HTML templates ─────────────────────────────────────────────────────────────

_BASE = """
<div style="max-width:600px;margin:0 auto;font-family:Arial,Helvetica,sans-serif;background:#f5f5f5;padding:24px;">
  <div style="background:#0d0d0d;padding:24px 28px;border-radius:12px 12px 0 0;text-align:center;">
    <span style="font-size:32px;">✂️</span>
    <h1 style="color:#c9a84c;margin:8px 0 4px;font-size:20px;letter-spacing:2px;text-transform:uppercase;">{title}</h1>
    <p style="color:#666;margin:0;font-size:13px;">{shop}</p>
  </div>
  <div style="background:#fff;padding:28px 32px;border-radius:0 0 12px 12px;">
    {body}
  </div>
  <p style="text-align:center;color:#aaa;font-size:11px;margin-top:16px;">{SHOP_NAME} · Automated booking system</p>
</div>
""".strip()

def _row(label, value):
    return f"""
    <tr>
      <td style="padding:10px 0;border-bottom:1px solid #f0f0f0;color:#888;font-size:13px;width:38%;">{label}</td>
      <td style="padding:10px 0;border-bottom:1px solid #f0f0f0;font-size:14px;font-weight:600;">{value}</td>
    </tr>"""

def _cal_buttons(gcal: str, ics: str) -> str:
    return f"""
    <div style="margin-top:24px;display:flex;gap:12px;">
      <a href="{gcal}" style="flex:1;display:block;background:#4285F4;color:#fff;text-align:center;
         padding:13px 16px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:13px;">
        📅 Add to Google Calendar
      </a>
      <a href="{ics}" style="flex:1;display:block;background:#1a1a1a;color:#c9a84c;text-align:center;
         padding:13px 16px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:13px;">
        📁 Download .ics (Apple / Outlook)
      </a>
    </div>"""

def _booking_table(b: dict) -> str:
    return f"""
    <table style="width:100%;border-collapse:collapse;">
      {_row("Customer",  b.get("customer_name", "—"))}
      {_row("Phone",     b.get("customer_phone", "—"))}
      {_row("Email",     b.get("customer_email") or "Not provided")}
      {_row("Service",   b.get("service_name", "—"))}
      {_row("Date",      b.get("booking_date", "—"))}
      {_row("Time",      b.get("booking_time", "—"))}
      {_row("Total",     f"£{b.get('price_gbp', 0)}")}
      {_row("Booking #", str(b.get("id", "—")))}
    </table>"""


def _owner_new_booking_html(b: dict, gcal: str, ics: str) -> str:
    body = f"""
    <p style="color:#555;margin:0 0 20px;">A new booking has been made and is <strong>awaiting payment</strong>.</p>
    {_booking_table(b)}
    <div style="margin-top:20px;padding:14px 16px;background:#fff8e1;border-left:4px solid #c9a84c;border-radius:4px;">
      <strong>⏳ Status:</strong> Payment not yet received. Slot is reserved for 30 minutes.
    </div>
    {_cal_buttons(gcal, ics)}
    """
    return _BASE.format(title="New Booking", shop=SHOP_NAME, body=body, SHOP_NAME=SHOP_NAME)


def _owner_payment_html(b: dict, gcal: str, ics: str) -> str:
    body = f"""
    <p style="color:#555;margin:0 0 20px;">Payment has been received. This appointment is <strong>confirmed</strong>.</p>
    {_booking_table(b)}
    <div style="margin-top:20px;padding:14px 16px;background:#e8f5e9;border-left:4px solid #4caf50;border-radius:4px;">
      <strong>✅ Paid:</strong> £{b.get('price_gbp', 0)} received via Stripe.
    </div>
    {_cal_buttons(gcal, ics)}
    """
    return _BASE.format(title="Payment Confirmed", shop=SHOP_NAME, body=body, SHOP_NAME=SHOP_NAME)


def _customer_confirmed_html(b: dict, gcal: str, ics: str) -> str:
    body = f"""
    <p style="color:#555;margin:0 0 20px;">
      Your appointment is booked and paid. We'll see you soon!
    </p>
    {_booking_table(b)}
    <div style="margin-top:20px;padding:14px 16px;background:#e8f5e9;border-left:4px solid #4caf50;border-radius:4px;">
      <strong>✅ All confirmed.</strong> Add it to your calendar so you don't forget.
    </div>
    {_cal_buttons(gcal, ics)}
    <p style="margin-top:24px;color:#888;font-size:13px;">
      If you need to cancel or reschedule, please call us directly.
    </p>
    """
    return _BASE.format(title="You're Booked!", shop=SHOP_NAME, body=body, SHOP_NAME=SHOP_NAME)


def _cancellation_html(b: dict) -> str:
    body = f"""
    <p style="color:#555;margin:0 0 20px;">The following booking has been cancelled.</p>
    {_booking_table(b)}
    <div style="margin-top:20px;padding:14px 16px;background:#fce4ec;border-left:4px solid #e53935;border-radius:4px;">
      <strong>❌ Cancelled.</strong> The slot is now free for other bookings.
    </div>
    """
    return _BASE.format(title="Booking Cancelled", shop=SHOP_NAME, body=body, SHOP_NAME=SHOP_NAME)
