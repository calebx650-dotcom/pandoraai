"""SQLite helpers + schema + seed data for Spectofire."""
import sqlite3
import os
import secrets
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
    extinguisher_type TEXT,
    extinguisher_size TEXT,
    manufactured_date TEXT,
    last_service_date TEXT,
    qr_token TEXT UNIQUE,
    notes TEXT,
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
    inspection_id INTEGER,
    device_id INTEGER,
    item_id TEXT,
    filename TEXT NOT NULL,
    caption TEXT,
    uploaded_at TEXT NOT NULL,
    FOREIGN KEY(inspection_id) REFERENCES inspections(id),
    FOREIGN KEY(device_id) REFERENCES devices(id)
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

# Columns we may need to ADD to existing tables on upgrade
MIGRATIONS = [
    ("devices", "extinguisher_type", "TEXT"),
    ("devices", "extinguisher_size", "TEXT"),
    ("devices", "manufactured_date", "TEXT"),
    ("devices", "last_service_date", "TEXT"),
    ("devices", "qr_token", "TEXT"),
    ("devices", "notes", "TEXT"),
    ("inspection_photos", "device_id", "INTEGER"),
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_exists(conn, table, col):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == col for r in rows)


def init_db():
    fresh = not os.path.exists(DB_PATH)
    conn = get_conn()
    conn.executescript(SCHEMA)
    # Run safe ALTER TABLE migrations for existing DBs
    for table, col, ctype in MIGRATIONS:
        if not _column_exists(conn, table, col):
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ctype}")
                print(f"migrated: added {table}.{col}")
            except sqlite3.OperationalError as e:
                print(f"migration skipped for {table}.{col}: {e}")
    # Backfill qr_token for any extinguisher missing one
    rows = conn.execute(
        "SELECT id FROM devices WHERE (qr_token IS NULL OR qr_token='') AND device_type='extinguisher'"
    ).fetchall()
    for r in rows:
        conn.execute("UPDATE devices SET qr_token=? WHERE id=?",
                     (secrets.token_urlsafe(12), r["id"]))
    conn.commit()
    if fresh:
        seed(conn)
    conn.close()


def log_event(user_id, action, target_type=None, target_id=None, detail=None):
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
    today = datetime.utcnow().date()

    users = [
        ("inspector", "igh2026", "Brandon Russ", "inspector"),
        ("admin", "igh2026", "Brent (Owner)", "admin"),
    ]
    for u, p, name, role in users:
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            (u, generate_password_hash(p), name, role),
        )

    sites = [
        ("Excel 4 Construction", "Building #2 1710 Couch Dr.",
         "1710 Couch Dr, McKinney TX 75069",
         "Foreman Kyle", "(469) 555-0190",
         "Active hot-work; firewatch required while sprinkler riser is offline."),
        ("Lone Star BBQ", "Plano Restaurant", "1450 Preston Rd, Plano TX 75093",
         "Maria Lopez", "(972) 555-0143", "Kitchen + dining; semi-annual hood inspection."),
        ("Cedar Hill ISD", "High School Gym", "1801 Cedar Hill Rd, Cedar Hill TX 75104",
         "Coach Daniels", "(469) 555-0102", "Annual extinguisher & alarm checks."),
        ("Sunrise Senior Living", "Frisco Memory Care", "5151 Eldorado Pkwy, Frisco TX 75033",
         "Karen Mills, RN", "(214) 555-0188", "Quarterly walk; many residents."),
        ("Metroplex Logistics", "Arlington Warehouse", "2200 E Lamar Blvd, Arlington TX 76011",
         "Devon Park", "(817) 555-0166", "Forklift bays, sprinkler riser room."),
    ]
    for s in sites:
        conn.execute(
            """INSERT INTO sites (customer_name, site_name, address, contact_name, contact_phone, notes, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (*s, now),
        )

    # Extinguishers with manufactured/serviced dates so 7-yr tracking has data to show.
    # Using 8 years ago for one to trigger the "expired" warning.
    def d(years_ago):
        return (today - timedelta(days=years_ago * 365)).isoformat()

    devices = [
        # site_id, device_type, barcode, model, serial, location, last_inspected, next_due,
        # ext_type, size, manufactured, last_service, qr_token, notes
        (2, "extinguisher", "IGH-FE-00112", "Amerex B402", "AX-7782991",
         "Front of house - by host stand",
         (today - timedelta(days=350)).isoformat(),
         (today + timedelta(days=15)).isoformat(),
         "ABC Dry Chemical", "5 lb", d(3), d(1), secrets.token_urlsafe(12),
         "Dining room main extinguisher."),
        (2, "extinguisher", "IGH-FE-00113", "Amerex K01", "AX-K-441120",
         "Kitchen line - Class K",
         (today - timedelta(days=350)).isoformat(),
         (today + timedelta(days=15)).isoformat(),
         "Class K (Wet Chemical)", "6 L", d(2), d(0), secrets.token_urlsafe(12),
         "Class K for cooking oil fires."),
        (3, "extinguisher", "IGH-FE-00200", "Amerex B500", "AX-7780221",
         "Gym east exit",
         (today - timedelta(days=200)).isoformat(),
         (today + timedelta(days=165)).isoformat(),
         "ABC Dry Chemical", "10 lb", d(4), d(1), secrets.token_urlsafe(12), None),
        (5, "extinguisher", "IGH-FE-00301", "Amerex B500", "AX-7790012",
         "Loading dock 1",
         (today - timedelta(days=400)).isoformat(),
         (today - timedelta(days=35)).isoformat(),
         "ABC Dry Chemical", "10 lb", d(8), d(2), secrets.token_urlsafe(12),
         "Hydrostatic test overdue - flagged for service."),
        (5, "extinguisher", "IGH-FE-00302", "Amerex B500", "AX-7790013",
         "Loading dock 2",
         (today - timedelta(days=400)).isoformat(),
         (today - timedelta(days=35)).isoformat(),
         "ABC Dry Chemical", "10 lb", d(7), d(3), secrets.token_urlsafe(12),
         "At 7-yr mark - schedule hydrostatic."),
        (3, "fire_alarm_panel", "IGH-FA-0010", "Notifier NFS2-640", "NF-44120",
         "Main electrical room",
         (today - timedelta(days=300)).isoformat(),
         (today + timedelta(days=65)).isoformat(),
         None, None, None, None, None, None),
        (4, "emergency_light", "IGH-EL-0540", "Lithonia ELM2", "LTH-22-9911",
         "North corridor",
         (today - timedelta(days=20)).isoformat(),
         (today + timedelta(days=345)).isoformat(),
         None, None, None, None, None, None),
        (2, "kitchen_suppression", "IGH-KS-0021", "Ansul R-102", "ANS-009842",
         "Hood over flat-top",
         (today - timedelta(days=170)).isoformat(),
         (today + timedelta(days=10)).isoformat(),
         None, None, None, None, None, None),
    ]
    for d_row in devices:
        conn.execute(
            """INSERT INTO devices (site_id, device_type, barcode, model, serial, location,
                                    last_inspected, next_due,
                                    extinguisher_type, extinguisher_size, manufactured_date,
                                    last_service_date, qr_token, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            d_row,
        )

    # An in-progress fire-extinguisher inspection at Excel 4 Construction
    conn.execute(
        """INSERT INTO inspections (site_id, inspector_id, template_slug, status, started_at, gps_lat, gps_lng, notes)
           VALUES (?,?,?,?,?,?,?,?)""",
        (1, 1, "fire_extinguisher", "in_progress", now, 33.1976, -96.6155,
         "Walkthrough at 1710 Couch Dr."),
    )

    # A completed fire-alarm inspection
    completed_at = (datetime.utcnow() - timedelta(days=2)).isoformat(timespec="seconds")
    started_earlier = (datetime.utcnow() - timedelta(days=2, hours=1)).isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO inspections (site_id, inspector_id, template_slug, status, started_at, completed_at,
                                    gps_lat, gps_lng, inspector_signature, customer_signature, customer_email)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (3, 1, "fire_alarm", "completed", started_earlier, completed_at,
         32.5887, -96.9561, "Brandon Russ", "Coach Daniels", "facilities@chisd.example"),
    )

    # An active firewatch shift at Excel 4 Construction
    conn.execute(
        """INSERT INTO inspections (site_id, inspector_id, template_slug, status, started_at, gps_lat, gps_lng, notes)
           VALUES (?,?,?,?,?,?,?,?)""",
        (1, 1, "firewatch", "in_progress",
         (datetime.utcnow() - timedelta(hours=9)).isoformat(timespec="seconds"),
         33.1976, -96.6155, "Hot-work on level 4. 15-min interval rounds."),
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

    # Sample firewatch rounds (15-min intervals from 0815) for inspection id 3
    base = datetime.utcnow().replace(hour=8, minute=15, second=0, microsecond=0)
    for n in range(1, 13):
        ts = (base + timedelta(minutes=15 * (n - 1))).isoformat(timespec="seconds")
        conn.execute(
            """INSERT INTO firewatch_rounds (inspection_id, round_no, started_at, location, observations, all_clear, gps_lat, gps_lng)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (3, n, ts,
             ["Level 4 - hot work zone", "Stairwell B", "Roof access", "Loading dock"][n % 4],
             "", 1, 33.1976, -96.6155),
        )

    conn.execute(
        """INSERT INTO inspection_comments (inspection_id, user_id, body, created_at)
           VALUES (?, ?, ?, ?)""",
        (3, 2, "City inspector swinging by around 2pm. Keep notes tight.",
         (datetime.utcnow() - timedelta(hours=1)).isoformat(timespec="seconds")),
    )

    for action, tt, tid, detail, mins in [
        ("login", "user", 1, "Brandon Russ signed in", 130),
        ("inspection_started", "inspection", 1, "Excel 4 Construction - extinguisher", 120),
        ("inspection_completed", "inspection", 2, "Cedar Hill ISD - alarm", 60 * 24 * 2),
        ("firewatch_started", "inspection", 3, "Excel 4 Construction - hot work", 540),
    ]:
        ts = (datetime.utcnow() - timedelta(minutes=mins)).isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO events (user_id, action, target_type, target_id, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (1, action, tt, tid, detail, ts),
        )

    conn.commit()
