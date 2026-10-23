# AI Booking & Payments Agent

An end to end AI booking product for a small service business (barbershop use case): a conversational agent books appointments, takes payment through Stripe, and triggers automated notifications, with an admin dashboard for the owner.

## What it does
- **Conversational booking agent** (LangGraph ReAct + Groq): guides the customer step by step (service, date, time, name, phone, email), checks real availability, and creates the booking.
- **Typed tools over a SQL database**: `get_services`, `check_availability`, `create_booking`.
- **Guardrails**: strict step by step workflow, one question per message, and the booking is only created after the customer explicitly confirms.
- **Structured output contract**: the agent ends with a `BOOKING_ID:<id>` tag that the backend parses reliably to start payment.
- **Payments**: Stripe Checkout plus webhook confirmation.
- **Automations**: non blocking n8n webhooks for new booking alerts, payment confirmations and a daily summary.
- **Admin dashboard**: view and manage bookings (password protected).

## Architecture
```
Customer chat ──► FastAPI ──► LangGraph agent ──► tools ──► SQLite
                     │                                   
                     ├──► Stripe Checkout ──► webhook ──► mark paid
                     └──► n8n webhooks (alerts, daily summary) · email notifications
```

## Tech stack
Python · FastAPI · LangGraph · Groq · SQLite · Stripe · n8n · Docker / docker compose · HTML/CSS/JS

## Run locally
```bash
cp .env.example .env        # add your keys (Groq, Stripe TEST keys) and set ADMIN_PASSWORD
docker compose up --build   # or: pip install -r requirements.txt && uvicorn main:app --reload
```
Open `http://localhost:8000` for the booking page and `/admin` for the dashboard.

## Security notes
Secrets live only in `.env` (git ignored). There is no default admin password: if `ADMIN_PASSWORD` is unset, the admin panel stays locked.
