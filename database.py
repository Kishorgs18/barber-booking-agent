import sqlite3
from contextlib import contextmanager

DB_PATH = "barber.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS services (
                id               INTEGER PRIMARY KEY,
                name             TEXT    NOT NULL,
                price_gbp        REAL    NOT NULL,
                duration_minutes INTEGER NOT NULL,
                description      TEXT
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id        INTEGER NOT NULL,
                customer_name     TEXT    NOT NULL,
                customer_phone    TEXT    NOT NULL,
                customer_email    TEXT    DEFAULT '',
                booking_date      TEXT    NOT NULL,
                booking_time      TEXT    NOT NULL,
                status            TEXT    DEFAULT 'pending_payment',
                payment_status    TEXT    DEFAULT 'unpaid',
                stripe_session_id TEXT,
                created_at        TEXT    DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (service_id) REFERENCES services(id)
            );
        """)

        if conn.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO services (id,name,price_gbp,duration_minutes,description) VALUES (?,?,?,?,?)",
                [
                    (1, "Haircut",                15.00, 30, "Classic cut styled to your preference"),
                    (2, "Beard Trim",              10.00, 20, "Precision shaping and line-up"),
                    (3, "Haircut + Beard Trim",    22.00, 50, "Full grooming package — best value"),
                    (4, "Skin Fade",               18.00, 40, "Zero to skin fade, any style"),
                    (5, "Kids Cut (Under 12)",     10.00, 25, "Gentle cut for the little ones"),
                ],
            )
