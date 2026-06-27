from datetime import date, timedelta
from typing import Optional
import json
import stripe
import httpx

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database as db
import agent as ag
import notifications as notif
from config import (
    STRIPE_SECRET_KEY, STRIPE_PUB_KEY, STRIPE_WEBHOOK_SEC,
    BASE_URL, SHOP_NAME, ADMIN_PASSWORD, N8N_WEBHOOK_BASE,
)

stripe.api_key = STRIPE_SECRET_KEY

app = FastAPI(title="Barber Booking Agent")
db.init_db()
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── N8N webhook helper ─────────────────────────────────────────────────────────

async def _fire(event: str, payload: dict):
    """Fire a webhook to N8N in the background — non-blocking, silent on failure."""
    if not N8N_WEBHOOK_BASE:
        return
    url = f"{N8N_WEBHOOK_BASE.rstrip('/')}/{event}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json=payload)
    except Exception:
        pass


def _booking_payload(booking_id: int) -> dict:
    with db.get_conn() as conn:
        row = conn.execute(
            """SELECT b.*, s.name AS service_name, s.price_gbp
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.id = ?""",
            (booking_id,),
        ).fetchone()
    return dict(row) if row else {"booking_id": booking_id}


# ── Redirects ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return RedirectResponse("/static/index.html")

@app.get("/admin")
def admin_page():
    return RedirectResponse("/static/admin.html")

@app.get("/payment/success")
async def payment_success(session_id: str = "", background_tasks: BackgroundTasks = None):
    if not session_id:
        return RedirectResponse("/static/index.html")
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            booking_id = int(session.metadata["booking_id"])
            with db.get_conn() as conn:
                conn.execute(
                    "UPDATE bookings SET payment_status='paid', status='confirmed' WHERE id=?",
                    (booking_id,),
                )
            if background_tasks:
                payload = _booking_payload(booking_id)
                background_tasks.add_task(_fire, "barber-payment-confirmed", payload)
                background_tasks.add_task(notif.notify_payment_confirmed, payload)
            return RedirectResponse(f"/static/success.html?booking_id={booking_id}")
    except Exception:
        pass
    return RedirectResponse("/static/index.html")


# ── Chat ───────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str

@app.post("/api/chat")
async def chat(req: ChatRequest, background_tasks: BackgroundTasks):
    result = ag.chat(req.session_id, req.message)
    if result.get("booking_id"):
        payload = _booking_payload(result["booking_id"])
        background_tasks.add_task(_fire, "barber-new-booking", payload)
        background_tasks.add_task(notif.notify_new_booking, payload)
    return result


# ── Payments ───────────────────────────────────────────────────────────────────

@app.post("/api/payment/create-session/{booking_id}")
def create_payment_session(booking_id: int):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    with db.get_conn() as conn:
        row = conn.execute(
            """SELECT b.*, s.name AS service_name, s.price_gbp
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.id = ?""",
            (booking_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Booking not found")

    label = f"{row['service_name']} — {row['booking_date']} at {row['booking_time']}"
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "gbp",
                "product_data": {"name": label},
                "unit_amount": int(row["price_gbp"] * 100),
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=f"{BASE_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{BASE_URL}/",
        metadata={"booking_id": str(booking_id)},
        customer_email=row["customer_email"] or None,
    )

    with db.get_conn() as conn:
        conn.execute(
            "UPDATE bookings SET stripe_session_id=? WHERE id=?",
            (session.id, booking_id),
        )

    return {"url": session.url}


@app.post("/api/webhook/stripe")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        if STRIPE_WEBHOOK_SEC:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SEC)
        else:
            event = json.loads(payload)

        if event["type"] == "checkout.session.completed":
            s = event["data"]["object"]
            if s.get("payment_status") == "paid":
                booking_id = int(s["metadata"]["booking_id"])
                with db.get_conn() as conn:
                    conn.execute(
                        "UPDATE bookings SET payment_status='paid', status='confirmed' WHERE id=?",
                        (booking_id,),
                    )
                bp = _booking_payload(booking_id)
                background_tasks.add_task(_fire, "barber-payment-confirmed", bp)
                background_tasks.add_task(notif.notify_payment_confirmed, bp)
    except Exception:
        pass
    return {"status": "ok"}


# ── Admin ──────────────────────────────────────────────────────────────────────

@app.get("/api/admin/bookings")
def get_bookings(date: Optional[str] = None, password: str = ""):
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorised")

    with db.get_conn() as conn:
        if date:
            rows = conn.execute(
                """SELECT b.*, s.name AS service_name, s.price_gbp
                   FROM bookings b JOIN services s ON b.service_id = s.id
                   WHERE b.booking_date = ?
                   ORDER BY b.booking_time""",
                (date,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT b.*, s.name AS service_name, s.price_gbp
                   FROM bookings b JOIN services s ON b.service_id = s.id
                   ORDER BY b.booking_date DESC, b.booking_time
                   LIMIT 200"""
            ).fetchall()

    return [dict(r) for r in rows]


@app.patch("/api/admin/bookings/{booking_id}")
async def update_booking(booking_id: int, request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    if data.get("password", "") != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorised")

    new_status = data.get("status", "")
    if new_status not in ("confirmed", "cancelled", "completed"):
        raise HTTPException(status_code=400, detail="Invalid status")

    with db.get_conn() as conn:
        conn.execute("UPDATE bookings SET status=? WHERE id=?", (new_status, booking_id))

    payload = _booking_payload(booking_id)
    payload["new_status"] = new_status
    background_tasks.add_task(_fire, f"barber-status-{new_status}", payload)
    if new_status == "cancelled":
        background_tasks.add_task(notif.notify_cancellation, payload)

    return {"ok": True}


# ── Stats (N8N polls this for daily summary) ───────────────────────────────────

@app.get("/api/stats")
def get_stats(password: str = ""):
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorised")

    today_str = date.today().isoformat()

    with db.get_conn() as conn:
        today = conn.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN payment_status='paid' THEN 1 ELSE 0 END) as paid,
                      SUM(CASE WHEN payment_status='paid' THEN s.price_gbp ELSE 0 END) as revenue
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.booking_date = ? AND b.status != 'cancelled'""",
            (today_str,),
        ).fetchone()

        week_revenue = conn.execute(
            """SELECT COALESCE(SUM(s.price_gbp), 0) as revenue
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.booking_date >= ? AND b.payment_status='paid'""",
            ((date.today() - timedelta(days=7)).isoformat(),),
        ).fetchone()

        popular = conn.execute(
            """SELECT s.name, COUNT(*) as cnt
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.status != 'cancelled'
               GROUP BY s.name ORDER BY cnt DESC LIMIT 1""",
        ).fetchone()

    return {
        "date": today_str,
        "today_total": today["total"] or 0,
        "today_paid": today["paid"] or 0,
        "today_revenue_gbp": round(today["revenue"] or 0, 2),
        "week_revenue_gbp": round(week_revenue["revenue"] or 0, 2),
        "most_popular_service": popular["name"] if popular else "N/A",
        "shop_name": SHOP_NAME,
    }


# ── Upcoming bookings (N8N polls for reminder workflow) ────────────────────────

@app.get("/api/upcoming-bookings")
def upcoming_bookings(days_ahead: int = 1, password: str = ""):
    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorised")

    target = (date.today() + timedelta(days=days_ahead)).isoformat()

    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT b.*, s.name AS service_name, s.price_gbp
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.booking_date = ? AND b.status = 'confirmed'
               ORDER BY b.booking_time""",
            (target,),
        ).fetchall()

    return {"date": target, "bookings": [dict(r) for r in rows]}


# ── Public booking lookup + calendar download ──────────────────────────────────

@app.get("/api/booking/{booking_id}")
def get_booking(booking_id: int):
    with db.get_conn() as conn:
        row = conn.execute(
            """SELECT b.*, s.name AS service_name, s.price_gbp, s.duration_minutes
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.id = ?""",
            (booking_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return dict(row)


@app.get("/api/booking/{booking_id}/calendar.ics")
def download_ics(booking_id: int):
    from fastapi.responses import Response
    with db.get_conn() as conn:
        row = conn.execute(
            """SELECT b.*, s.name AS service_name, s.price_gbp, s.duration_minutes
               FROM bookings b JOIN services s ON b.service_id = s.id
               WHERE b.id = ?""",
            (booking_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    ics = notif.ics_content(dict(row))
    return Response(
        content=ics,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="booking-{booking_id}.ics"'},
    )


# ── Config ─────────────────────────────────────────────────────────────────────

@app.get("/api/config")
def get_config():
    return {"shop_name": SHOP_NAME, "stripe_pub_key": STRIPE_PUB_KEY}
