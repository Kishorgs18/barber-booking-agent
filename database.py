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
                    # ── Classic Haircuts ──────────────────────────────────────
                    (1,  "Haircut",                        15.00, 30,  "Classic cut styled to your preference"),
                    (2,  "Skin Fade",                      18.00, 40,  "Zero to skin fade — any style"),
                    (3,  "Taper Fade",                     18.00, 40,  "Gradual taper, clean and sharp finish"),
                    (4,  "Drop Fade",                      18.00, 40,  "Fade that drops behind the ear"),
                    (5,  "Low Fade",                       16.00, 35,  "Subtle fade starting just above the ear"),
                    (6,  "Mid Fade",                       17.00, 35,  "Fade starting at the temple level"),
                    (7,  "High Fade",                      18.00, 40,  "Fade starting high on the sides"),
                    (8,  "Buzz Cut",                       12.00, 20,  "All-over clipper cut, clean finish"),
                    (9,  "Crew Cut",                       14.00, 25,  "Short back and sides, longer on top"),
                    (10, "Undercut",                       16.00, 35,  "Disconnected undercut — shaved sides, styled top"),
                    (11, "Pompadour",                      18.00, 40,  "Classic voluminous style swept back"),
                    (12, "Quiff",                          16.00, 35,  "Modern quiff — scissor or clipper finish"),
                    (13, "Mohawk",                         18.00, 40,  "Shaved sides with central strip styled up"),
                    (14, "Caesar Cut",                     14.00, 30,  "Short fringe, uniform length all over"),
                    (15, "French Crop",                    15.00, 30,  "Short textured top with faded sides"),
                    (16, "Textured Crop",                  16.00, 35,  "Modern crop with texture and movement"),
                    (17, "Slick Back",                     16.00, 35,  "Hair slicked back with product finish"),
                    (18, "Head Shave (Bald)",              13.00, 25,  "Full wet or dry head shave, razor smooth"),
                    # ── Specialist Cuts ───────────────────────────────────────
                    (19, "Afro Cut",                       20.00, 45,  "Shape and style for afro hair"),
                    (20, "Curly Hair Cut",                 18.00, 40,  "Cut and style for curly and wavy hair"),
                    (21, "Waves / 360 Waves",              20.00, 45,  "Brush waves cut and styled"),
                    (22, "Locs Trim",                      20.00, 40,  "Trim and shape existing dreadlocks"),
                    (23, "Locs Retwist",                   25.00, 60,  "Retwist and neaten dreadlocks"),
                    (24, "Locs Start (Starter Locs)",      35.00, 90,  "Begin your loc journey from scratch"),
                    (25, "Two-Strand Twist",               25.00, 60,  "Two-strand twists on natural hair"),
                    (26, "Cornrows (Simple)",              25.00, 60,  "Straight-back cornrow braids"),
                    (27, "Cornrows (Designs)",             40.00, 90,  "Cornrows with patterns and designs"),
                    (28, "Box Braids",                     50.00, 120, "Individual box braids — price varies by length"),
                    # ── Concession Cuts ───────────────────────────────────────
                    (29, "Kids Cut (Under 12)",            10.00, 25,  "Gentle cut for the little ones"),
                    (30, "Toddler Cut (Under 5)",           8.00, 20,  "Patient and gentle cut for toddlers"),
                    (31, "First Haircut",                  10.00, 20,  "Baby's or toddler's very first cut"),
                    (32, "Senior Cut (60+)",               12.00, 30,  "Classic cut at a senior rate"),
                    (33, "Student Cut",                    13.00, 30,  "Student discount — valid ID required"),
                    # ── Beard & Face ──────────────────────────────────────────
                    (34, "Beard Trim & Shape",             10.00, 20,  "Clean shaping and line-up of your beard"),
                    (35, "Full Beard Sculpt",              15.00, 30,  "Full reshape, define, and style"),
                    (36, "Hot Towel Shave",                18.00, 30,  "Traditional straight razor shave with hot towel"),
                    (37, "Dry Shave",                      12.00, 20,  "Quick razor shave without hot towel"),
                    (38, "Moustache Trim",                  5.00, 10,  "Neat trim and shape of moustache"),
                    (39, "Goatee Trim",                     8.00, 15,  "Goatee shaped and defined"),
                    (40, "Beard Colour / Tint",            15.00, 30,  "Colour applied to beard — cover grey or darken"),
                    (41, "Beard Straightening",            20.00, 30,  "Keratin-based beard straightening treatment"),
                    (42, "Nose Hair Trim",                  5.00, 10,  "Discreet nose hair removal"),
                    (43, "Ear Hair Trim",                   5.00, 10,  "Ear hair tidied up"),
                    (44, "Eyebrow Trim",                    5.00, 10,  "Clean and shape the eyebrows"),
                    (45, "Eyebrow Threading",               6.00, 10,  "Precise eyebrow shaping via threading"),
                    (46, "Face Mask Treatment",            12.00, 20,  "Deep cleanse face mask applied post-shave"),
                    # ── Combo Packages ────────────────────────────────────────
                    (47, "Haircut + Beard Trim",           22.00, 50,  "Classic combo — cut and beard shaped"),
                    (48, "Haircut + Hot Towel Shave",      28.00, 60,  "Premium combo — cut plus luxury shave"),
                    (49, "Skin Fade + Beard Trim",         25.00, 60,  "Fade and beard done together"),
                    (50, "Skin Fade + Hot Towel Shave",    30.00, 70,  "Top package — fade plus classic hot towel shave"),
                    (51, "Full Groom Package",             35.00, 80,  "Fade + beard sculpt + hot towel + eyebrow trim"),
                    (52, "Groom / Wedding Package",        50.00, 90,  "Full premium groom for your big day"),
                    (53, "Executive Cut",                  25.00, 45,  "Premium cut with scalp massage and styling"),
                    # ── Hair Add-ons ──────────────────────────────────────────
                    (54, "Hair Design / Pattern",           5.00, 10,  "Razor art or pattern cut into hair"),
                    (55, "Shape Up / Line Up",              8.00, 15,  "Crisp lines — forehead, temples, neckline"),
                    (56, "Hair Wash & Blow Dry",            8.00, 15,  "Shampoo, condition, and blow dry"),
                    (57, "Scalp Massage",                   8.00, 15,  "Relaxing scalp massage — great add-on"),
                    (58, "Scalp Treatment",                12.00, 20,  "Moisturising treatment for dry or itchy scalp"),
                    # ── Hair Colour ───────────────────────────────────────────
                    (59, "Hair Colour / Tint",             25.00, 60,  "Single colour — discuss shade on arrival"),
                    (60, "Grey Coverage",                  20.00, 45,  "Cover grey hairs with matching colour"),
                    (61, "Highlights / Frosted Tips",      30.00, 60,  "Foil highlights or frosted tips"),
                    (62, "Bleach & Tone",                  35.00, 75,  "Full bleach and toner for platinum or fashion colours"),
                    (63, "Henna Colour",                   20.00, 60,  "Natural henna colour for hair or beard"),
                    # ── Hair Treatments ───────────────────────────────────────
                    (64, "Deep Condition Treatment",       15.00, 20,  "Intensive conditioning mask for dry or damaged hair"),
                    (65, "Hot Oil Treatment",              12.00, 20,  "Nourishing hot oil for scalp and hair health"),
                    (66, "Keratin Treatment",              45.00, 90,  "Smoothing keratin to reduce frizz for up to 3 months"),
                    (67, "Hair Relaxer",                   35.00, 60,  "Chemical relaxer to straighten afro or curly hair"),
                ],
            )
