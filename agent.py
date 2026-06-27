import json
import os
import re
from datetime import date, datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent

import database as db
from config import GROQ_API_KEY, SHOP_NAME

os.environ.setdefault("GROQ_API_KEY", GROQ_API_KEY)

# In-memory sessions: session_id -> list of messages
_sessions: dict[str, list] = {}

SYSTEM_PROMPT = """You are a warm, professional booking assistant called Max for {shop_name}, a barbershop.
Your only job is to help customers book appointments — nothing else.

BOOKING FLOW (always follow this order):
1. Greet the customer and ask which service they'd like.
2. Call get_services to display the menu with prices.
3. Confirm the service they chose.
4. Ask for their preferred date (we open Mon–Sat, 9 am – 7 pm; closed Sundays).
5. Call check_availability with that date in YYYY-MM-DD format.
6. Show a few good time slots and let them pick one.
7. Ask for their full name (one question at a time).
8. Ask for their phone number.
9. Ask for their email — say it's optional, just for a digital receipt.
10. Read back a short summary and ask them to confirm.
11. Call create_booking with all the details.
12. Tell them their spot is reserved and to click the Pay Now button to lock it in.

RULES:
- Short messages only — 1 to 3 sentences per reply. Never write walls of text.
- Never ask for two pieces of information in the same message.
- Use £ for prices. British spelling throughout.
- Today is {today}. When someone says "Saturday" or "tomorrow", convert to an exact YYYY-MM-DD date.
- If a day is fully booked, apologise briefly and suggest the next available weekday.
- Do not discuss anything unrelated to booking.
- Only call create_booking after the customer has explicitly confirmed all details.
- After create_booking succeeds, end your response with this exact tag on its own line:
  BOOKING_ID:<the integer id from the tool result>
- If the first message is "__start__", send your opening greeting without referencing it.
"""


@tool
def get_services() -> str:
    """Returns all available barbershop services with id, name, price (£), and duration."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, price_gbp, duration_minutes, description FROM services"
        ).fetchall()
    return json.dumps([dict(r) for r in rows])


@tool
def check_availability(date_str: str) -> str:
    """Returns available 30-minute appointment slots for a given date (YYYY-MM-DD)."""
    try:
        check = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return json.dumps({"error": "Invalid date — please use YYYY-MM-DD."})

    if check < date.today():
        return json.dumps({"error": "That date is in the past. Please pick a future date."})

    if check.weekday() == 6:
        return json.dumps({"error": "We are closed on Sundays. Please pick a Mon–Sat date."})

    all_slots = [
        f"{h:02d}:{m:02d}"
        for h in range(9, 19)
        for m in (0, 30)
    ]

    with db.get_conn() as conn:
        taken_rows = conn.execute(
            "SELECT booking_time FROM bookings WHERE booking_date=? AND status != 'cancelled'",
            (date_str,),
        ).fetchall()

    taken = {r["booking_time"] for r in taken_rows}
    available = [s for s in all_slots if s not in taken]

    if not available:
        return json.dumps({"date": date_str, "available_slots": [],
                           "message": "Fully booked on that day. Please try another."})

    return json.dumps({"date": date_str, "available_slots": available})


@tool
def create_booking(
    service_id: int,
    customer_name: str,
    customer_phone: str,
    booking_date: str,
    booking_time: str,
    customer_email: str = "",
) -> str:
    """Creates a booking. Call only after customer confirms all details.
    Returns booking_id on success."""
    with db.get_conn() as conn:
        conflict = conn.execute(
            "SELECT id FROM bookings WHERE booking_date=? AND booking_time=? AND status != 'cancelled'",
            (booking_date, booking_time),
        ).fetchone()

        if conflict:
            return json.dumps({"error": "That slot was just taken. Please pick another time."})

        cur = conn.execute(
            """INSERT INTO bookings
               (service_id, customer_name, customer_phone, customer_email, booking_date, booking_time)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (service_id, customer_name, customer_phone, customer_email, booking_date, booking_time),
        )
        booking_id = cur.lastrowid

    return json.dumps({"booking_id": booking_id, "status": "pending_payment"})


_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)
        _agent = create_react_agent(llm, [get_services, check_availability, create_booking])
    return _agent


def chat(session_id: str, user_message: str) -> dict:
    today = datetime.today().strftime("%A, %-d %B %Y")

    if session_id not in _sessions:
        _sessions[session_id] = [
            SystemMessage(content=SYSTEM_PROMPT.format(shop_name=SHOP_NAME, today=today))
        ]

    _sessions[session_id].append(HumanMessage(content=user_message))

    try:
        result = _get_agent().invoke({"messages": _sessions[session_id]})
    except Exception as exc:
        return {"message": f"Sorry, something went wrong: {exc}", "booking_id": None, "show_payment": False}

    _sessions[session_id] = result["messages"]

    last = result["messages"][-1]
    text = last.content if hasattr(last, "content") else str(last)

    booking_id = None
    m = re.search(r"BOOKING_ID:(\d+)", text)
    if m:
        booking_id = int(m.group(1))
        text = re.sub(r"\n?BOOKING_ID:\d+", "", text).strip()

    return {
        "message": text,
        "booking_id": booking_id,
        "show_payment": booking_id is not None,
    }


def clear_session(session_id: str):
    _sessions.pop(session_id, None)
