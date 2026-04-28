"""SQLite helpers + schema + seed data for IGH fireNspec."""
import sqlite3
import os
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(__file__))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "firenspec.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'inspector'
);

CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    site_name TEXT NOT NULL,
    address TEXT,
    contact_name TEXT,
    contact_phone TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    device_type TEXT NOT NULL,
    barcode TEXT,
    model TEXT,
    serial TEXT,
    location TEXT,
    last_inspected TEXT,
    next_due TEXT,
    FOREIGN KEY(site_id) REFERENCES sites(id)
);

CREATE TABLE IF NOT EXISTS inspections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    inspector_id INTEGER NOT NULL,
    template_slug TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'in_progress',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    gps_lat REAL,
    gps_lng REAL,
    inspector_signature TEXT,
    customer_signature TEXT,
    customer_email TEXT,
    notes TEXT,
    device_id INTEGER,
    FOREIGN KEY(site_id) REFERENCES sites(id),
    FOREIGN KEY(inspector_id) REFERENCES users(id),
    FOREIGN KEY(device_id) REFERENCES devices(id)
);

CREATE TABLE IF NOT EXISTS inspection_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id INTEGER NOT NULL,
    item_id TEXT NOT NULL,
    result TEXT,
    note TEXT,
    UNIQUE(inspection_id, item_id),
    FOREIGN KEY(inspection_id) REFERENCES inspections(id)
);

CREATE TABLE IF NOT EXISTS firewatch_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id INTEGER NOT NULL,
    round_no INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    location TEXT,
    observations TEXT,
    all_clear INTEGER NOT NULL DEFAULT 1,
    gps_lat REAL,
    gps_lng REAL,
    FOREIGN KEY(inspection_id) REFERENCES inspections(id)
);

CREATE TABLE IF NOT EXISTS inspection_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id INTEGER NOT NULL,
    item_id TEXT,
    filename TEXT NOT NULL,
    caption TEXT,
    uploaded_at TEXT NOT NULL,
    FOREIGN KEY(inspection_id) REFERENCES inspections(id)
);

CREATE TABLE IF NOT EXISTS inspection_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(inspection_id) REFERENCES inspections(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id INTEGER,
    detail TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    fresh = not os.path.exists(DB_PATH)
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    if fresh:
        seed(conn)
    conn.close()


def log_event(user_id, action, target_type=None, target_id=None, detail=None):
    """Append an entry to the global activity / audit log."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO events (user_id, action, target_type, target_id, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, action, target_type, target_id, detail,
         datetime.utcnow().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def seed(conn):
    now = datetime.utcnow().isoformat(timespec="seconds")

    users = [
        ("inspector", "igh2026", "Jordan Reyes", "inspector"),
        ("admin", "igh2026", "Brent (Owner)", "admin"),
    ]
    for u, p, name, role in users:
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            (u, generate_password_hash(p), name, role),
        )

    sites = [
        ("Lone Star BBQ", "Plano Restaurant", "1450 Preston Rd, Plano TX 75093",
         "Maria Lopez", "(972) 555-0143", "Kitchen + dining; semi-annual hood inspection."),
        ("Cedar Hill ISD", "High School Gym", "1801 Cedar Hill Rd, Cedar Hill TX 75104",
         "Coach Daniels", "(469) 555-0102", "Annual extinguisher & alarm checks."),
        ("Sunrise Senior Living", "Frisco Memory Care", "5151 Eldorado Pkwy, Frisco TX 75033",
         "Karen Mills, RN", "(214) 555-0188", "Quarterly walk; many residents - keep alarm tests brief."),
        ("Metroplex Logistics", "Arlington Warehouse", "2200 E Lamar Blvd, Arlington TX 76011",
         "Devon Park", "(817) 555-0166", "Forklift bays, sprinkler riser room near loading dock."),
        ("McKinney Construction Co.", "Tower Construction Site",
         "300 N Tennessee St, McKinney TX 75069",
         "Foreman Kyle", "(469) 555-0190",
         "Active hot-work; firewatch required while sprinkler riser is offline."),
    ]
    for s in sites:
        conn.execute(
            """INSERT INTO sites (customer_name, site_name, address, contact_name, contact_phone, notes, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (*s, now),
        )

    devices = [
        (1, "extinguisher", "IGH-FE-00112", "Amerex B402", "AX-7782991", "Front of house - by host stand",
         (datetime.utcnow() - timedelta(days=350)).date().isoformat(),
         (datetime.utcnow() + timedelta(days=15)).date().isoformat()),
        (1, "extinguisher", "IGH-FE-00113", "Amerex K01", "AX-K-441120", "Kitchen line - Class K",
         (datetime.utcnow() - timedelta(days=350)).date().isoformat(),
         (datetime.utcnow() + timedelta(days=15)).date().isoformat()),
        (1, "kitchen_suppression", "IGH-KS-0021", "Ansul R-102", "ANS-009842", "Hood over flat-top",
         (datetime.utcnow() - timedelta(days=170)).date().isoformat(),
         (datetime.utcnow() + timedelta(days=10)).date().isoformat()),
        (2, "extinguisher", "IGH-FE-00200", "Amerex B500", "AX-7780221", "Gym east exit",
         (datetime.utcnow() - timedelta(days=200)).date().isoformat(),
         (datetime.utcnow() + timedelta(days=165)).date().isoformat()),
        (2, "fire_alarm_panel", "IGH-FA-0010", "Notifier NFS2-640", "NF-44120", "Main electrical room",
         (datetime.utcnow() - timedelta(days=300)).date().isoformat(),
         (datetime.utcnow() + timedelta(days=65)).date().isoformat()),
        (3, "emergency_light", "IGH-EL-0540", "Lithonia ELM2", "LTH-22-9911", "North corridor",
         (datetime.utcnow() - timedelta(days=20)).date().isoformat(),
         (datetime.utcnow() + timedelta(days=345)).date().isoformat()),
        (4, "extinguisher", "IGH-FE-00301", "Amerex B500", "AX-7790012", "Loading dock 1",
         (datetime.utcnow() - timedelta(days=400)).date().isoformat(),
         (datetime.utcnow() - timedelta(days=35)).date().isoformat()),
        (4, "extinguisher", "IGH-FE-00302", "Amerex B500", "AX-7790013", "Loading dock 2",
         (datetime.utcnow() - timedelta(days=400)).date().isoformat(),
         (datetime.utcnow() - timedelta(days=35)).date().isoformat()),
    ]
    for d in devices:
        conn.execute(
            """INSERT INTO devices (site_id, device_type, barcode, model, serial, location, last_inspected, next_due)
               VALUES (?,?,?,?,?,?,?,?)""",
            d,
        )

    conn.execute(
        """INSERT INTO inspections (site_id, inspector_id, template_slug, status, started_at, gps_lat, gps_lng, notes)
           VALUES (?,?,?,?,?,?,?,?)""",
        (1, 1, "fire_extinguisher", "in_progress", now, 33.0198, -96.6989,
         "Started morning round - back to finish after lunch."),
    )
    completed_at = (datetime.utcnow() - timedelta(days=2)).isoformat(timespec="seconds")
    started_earlier = (datetime.utcnow() - timedelta(days=2, hours=1)).isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO inspections (site_id, inspector_id, template_slug, status, started_at, completed_at,
                                    gps_lat, gps_lng, inspector_signature, customer_signature, customer_email)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (2, 1, "fire_alarm", "completed", started_earlier, completed_at,
         32.5887, -96.9561, "Jordan Reyes", "Coach Daniels", "facilities@chisd.example"),
    )
    # An active firewatch shift at the McKinney site
    conn.execute(
        """INSERT INTO inspections (site_id, inspector_id, template_slug, status, started_at, gps_lat, gps_lng, notes)
           VALUES (?,?,?,?,?,?,?,?)""",
        (5, 1, "firewatch", "in_progress",
         (datetime.utcnow() - timedelta(hours=2)).isoformat(timespec="seconds"),
         33.1976, -96.6155, "Hot-work on level 4. 30-min interval rounds."),
    )

    from templates_data import all_items
    for item in all_items("fire_alarm"):
        if item["type"] != "check":
            continue
        result = "fail" if item["id"] == "fa_strobes" else "pass"
        conn.execute(
            "INSERT INTO inspection_items (inspection_id, item_id, result, note) VALUES (?,?,?,?)",
            (2, item["id"], result,
             "Strobes in north hall out of sync - work order #4412 created." if result == "fail" else None),
        )

    # Sample firewatch rounds for the active shift (inspection id 3)
    base = datetime.utcnow() - timedelta(hours=2)
    for n in range(1, 5):
        ts = (base + timedelta(minutes=30 * (n - 1))).isoformat(timespec="seconds")
        conn.execute(
            """INSERT INTO firewatch_rounds (inspection_id, round_no, started_at, location, observations, all_clear, gps_lat, gps_lng)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (3, n, ts,
             ["Level 4 - hot work zone", "Stairwell B", "Roof access", "Loading dock"][n - 1],
             ["No smoke/sparks observed.", "Clear.", "Clear.", "Clear."][n - 1],
             1, 33.1976, -96.6155),
        )

    # A welcome comment
    conn.execute(
        """INSERT INTO inspection_comments (inspection_id, user_id, body, created_at)
           VALUES (?, ?, ?, ?)""",
        (3, 2, "Heads up - city inspector swinging by around 2pm. Keep notes tight.",
         (datetime.utcnow() - timedelta(hours=1)).isoformat(timespec="seconds")),
    )

    # Sample events
    for action, tt, tid, detail, mins in [
        ("login", "user", 1, "inspector signed in", 130),
        ("inspection_started", "inspection", 1, "Lone Star BBQ - extinguisher", 120),
        ("inspection_completed", "inspection", 2, "Cedar Hill ISD - alarm", 60 * 24 * 2),
        ("firewatch_started", "inspection", 3, "McKinney site - hot work", 120),
        ("round_logged", "inspection", 3, "Round #4", 5),
    ]:
        ts = (datetime.utcnow() - timedelta(minutes=mins)).isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO events (user_id, action, target_type, target_id, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1 if action == "login" else 1, action, tt, tid, detail, ts),
        )

    conn.commit()
