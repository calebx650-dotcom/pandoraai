"""IGH fireNspec - Flask MVP.

Run:
    pip install -r requirements.txt
    python app.py
"""
import os
import re
import io
import csv
import json
import secrets
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import quote
from werkzeug.utils import secure_filename
import qrcode

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    jsonify, flash, abort, send_from_directory,
)
from werkzeug.security import check_password_hash

from db import get_conn, init_db, log_event
from templates_data import TEMPLATES, get_template, all_items, save_overrides

app = Flask(__name__)
# In production set IGH_SECRET via `fly secrets set IGH_SECRET=...`
app.secret_key = os.environ.get("IGH_SECRET")
if not app.secret_key:
    if os.environ.get("FLASK_ENV") == "production":
        raise RuntimeError("IGH_SECRET must be set in production")
    app.secret_key = "dev-igh-firenspec-secret"
app.config["JSON_SORT_KEYS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB photo cap
# Uploads go on the persistent volume in production, fall back to repo dir for local dev
UPLOAD_DIR = os.path.join(os.environ.get("DATA_DIR", os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

init_db()


# Company info shown on every report (edit here or override via env vars)
COMPANY = {
    "name":    os.environ.get("COMPANY_NAME",    "IGH Health, Fire & Safety, LLC"),
    "address": os.environ.get("COMPANY_ADDRESS", "2719 Trail Oak Ct"),
    "city":    os.environ.get("COMPANY_CITY",    "Arlington"),
    "state":   os.environ.get("COMPANY_STATE",   "TX"),
    "zip":     os.environ.get("COMPANY_ZIP",     "76016"),
    "license": os.environ.get("COMPANY_LICENSE", "ECR-3372489"),
    "email":   os.environ.get("COMPANY_EMAIL",   "info@ighsafety.com"),
    "phone":   os.environ.get("COMPANY_PHONE",   "(817) 809-8677"),
}



# ---------- helpers ----------
def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get("user_role") != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_globals():
    return {
        "TEMPLATES": TEMPLATES,
        "current_user": session.get("user_name"),
        "current_role": session.get("user_role"),
        "now": datetime.utcnow(),
    }


@app.template_filter("fmtdate")
def fmtdate(value):
    if not value:
        return "-"
    try:
        if "T" in value:
            return datetime.fromisoformat(value).strftime("%b %d, %Y %I:%M %p")
        return datetime.fromisoformat(value).strftime("%b %d, %Y")
    except Exception:
        return value


@app.template_filter("relative")
def relative(value):
    if not value:
        return "-"
    try:
        d = datetime.fromisoformat(value)
        delta = datetime.utcnow() - d
        s = int(delta.total_seconds())
        if s < 60:    return f"{s}s ago"
        if s < 3600:  return f"{s // 60}m ago"
        if s < 86400: return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"
    except Exception:
        return value


@app.template_filter("days_until")
def days_until(value):
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value).date()
        return (d - datetime.utcnow().date()).days
    except Exception:
        return None


# ---------- auth ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_conn()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            session["user_role"] = user["role"]
            log_event(user["id"], "login", "user", user["id"], f"{user['full_name']} signed in")
            nxt = request.args.get("next") or url_for("dashboard")
            return redirect(nxt)
        flash("Invalid login. Try inspector / igh2026.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    if session.get("user_id"):
        log_event(session["user_id"], "logout")
    session.clear()
    return redirect(url_for("login"))


# ---------- dashboard ----------
@app.route("/")
@login_required
def dashboard():
    conn = get_conn()
    in_progress = conn.execute("""
        SELECT i.*, s.customer_name, s.site_name
        FROM inspections i JOIN sites s ON s.id = i.site_id
        WHERE i.status = 'in_progress' AND i.inspector_id = ?
        ORDER BY i.started_at DESC
    """, (session["user_id"],)).fetchall()
    recent = conn.execute("""
        SELECT i.*, s.customer_name, s.site_name
        FROM inspections i JOIN sites s ON s.id = i.site_id
        WHERE i.status = 'completed'
        ORDER BY i.completed_at DESC LIMIT 10
    """).fetchall()
    today = datetime.utcnow().date().isoformat()
    overdue = conn.execute("""
        SELECT d.*, s.customer_name, s.site_name FROM devices d
        JOIN sites s ON s.id = d.site_id
        WHERE d.next_due IS NOT NULL AND d.next_due < ?
        ORDER BY d.next_due ASC
    """, (today,)).fetchall()
    upcoming = conn.execute("""
        SELECT d.*, s.customer_name, s.site_name FROM devices d
        JOIN sites s ON s.id = d.site_id
        WHERE d.next_due IS NOT NULL AND d.next_due >= ? AND d.next_due <= ?
        ORDER BY d.next_due ASC
    """, (today, (datetime.utcnow().date() + timedelta(days=30)).isoformat())).fetchall()
    # Extinguishers approaching/past 7-yr hydrostatic test
    ext_rows = conn.execute("""
        SELECT d.*, s.customer_name, s.site_name FROM devices d
        JOIN sites s ON s.id = d.site_id
        WHERE d.device_type='extinguisher' AND d.manufactured_date IS NOT NULL
    """).fetchall()
    hydro_due = []
    for er in ext_rows:
        st, msg = expiration_status(dict(er))
        if st in ("overdue", "due-soon"):
            d = dict(er); d["exp_status"] = st; d["exp_msg"] = msg
            hydro_due.append(d)
    hydro_due.sort(key=lambda x: x.get("manufactured_date") or "")

    stats = {}
    stats["total_sites"] = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
    stats["open_deficiencies"] = conn.execute(
        "SELECT COUNT(*) FROM deficiencies WHERE status='open'").fetchone()[0]
    stats["open_inspections"] = conn.execute(
        "SELECT COUNT(*) FROM inspections WHERE status='in_progress'").fetchone()[0]
    stats["unpaid_invoices"] = conn.execute(
        "SELECT COUNT(*) FROM invoices WHERE status IN ('draft','sent')").fetchone()[0]
    stats["pending_approvals"] = conn.execute(
        "SELECT COUNT(*) FROM inspections WHERE status='completed' AND approval_status='pending'"
    ).fetchone()[0]
    # Inspector-side: their own work currently in pending / rejected state
    my_pending = conn.execute("""
        SELECT i.*, s.customer_name, s.site_name FROM inspections i
        JOIN sites s ON s.id = i.site_id
        WHERE i.inspector_id = ? AND i.status='completed' AND i.approval_status='pending'
        ORDER BY i.completed_at DESC LIMIT 6
    """, (session["user_id"],)).fetchall()
    my_rejected = conn.execute("""
        SELECT i.*, s.customer_name, s.site_name FROM inspections i
        JOIN sites s ON s.id = i.site_id
        WHERE i.inspector_id = ? AND i.approval_status='rejected'
        ORDER BY i.completed_at DESC LIMIT 6
    """, (session["user_id"],)).fetchall()
    stats["my_pending"] = len(my_pending)
    month_end = (datetime.utcnow().date() + timedelta(days=30)).isoformat()
    scheduled_due = conn.execute("""
        SELECT ss.*, s.customer_name, s.site_name
        FROM site_schedules ss JOIN sites s ON s.id = ss.site_id
        WHERE ss.next_due IS NOT NULL AND ss.next_due <= ?
        ORDER BY ss.next_due ASC
    """, (month_end,)).fetchall()
    conn.close()
    return render_template("dashboard.html",
        in_progress=in_progress, recent=recent, overdue=overdue, upcoming=upcoming,
        hydro_due=hydro_due, stats=stats, scheduled_due=scheduled_due,
        my_pending=my_pending, my_rejected=my_rejected)


# ---------- sites ----------
@app.route("/sites")
@login_required
def sites():
    q = request.args.get("q", "").strip()
    conn = get_conn()
    if q:
        rows = conn.execute("""
            SELECT s.*, COUNT(d.id) AS device_count FROM sites s
            LEFT JOIN devices d ON d.site_id = s.id
            WHERE s.customer_name LIKE ? OR s.site_name LIKE ? OR s.address LIKE ?
            GROUP BY s.id ORDER BY s.customer_name
        """, (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
    else:
        rows = conn.execute("""
            SELECT s.*, COUNT(d.id) AS device_count FROM sites s
            LEFT JOIN devices d ON d.site_id = s.id
            GROUP BY s.id ORDER BY s.customer_name
        """).fetchall()
    conn.close()
    return render_template("sites.html", sites=rows, q=q)


@app.route("/sites/new", methods=["GET", "POST"])
@login_required
def new_site():
    if request.method == "POST":
        f = request.form
        conn = get_conn()
        cur = conn.execute("""
            INSERT INTO sites (customer_name, site_name, address, contact_name, contact_phone, contact_email, notes, created_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (f.get("customer_name", "").strip(), f.get("site_name", "").strip(),
              f.get("address", "").strip(), f.get("contact_name", "").strip(),
              f.get("contact_phone", "").strip(), f.get("contact_email", "").strip(),
              f.get("notes", "").strip(),
              datetime.utcnow().isoformat(timespec="seconds")))
        site_id = cur.lastrowid
        conn.commit(); conn.close()
        log_event(session["user_id"], "site_created", "site", site_id,
                  f.get("customer_name", "").strip())
        flash("Site created.", "success")
        return redirect(url_for("site_detail", site_id=site_id))
    return render_template("new_site.html")


@app.route("/sites/<int:site_id>")
@login_required
def site_detail(site_id):
    conn = get_conn()
    site = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
    if not site:
        conn.close(); abort(404)
    devices = conn.execute(
        "SELECT * FROM devices WHERE site_id = ? ORDER BY device_type, location", (site_id,)
    ).fetchall()
    inspections = conn.execute("""
        SELECT i.*, u.full_name AS inspector_name FROM inspections i
        JOIN users u ON u.id = i.inspector_id
        WHERE i.site_id = ? ORDER BY i.started_at DESC
    """, (site_id,)).fetchall()
    devices_with_status = []
    for dv in devices:
        dvd = dict(dv)
        if dvd.get("device_type") == "extinguisher":
            st, msg = expiration_status(dvd)
            dvd["exp_status"] = st
            dvd["exp_msg"] = msg
        else:
            dvd["exp_status"] = "ok"; dvd["exp_msg"] = ""
        devices_with_status.append(dvd)
    conn.close()
    return render_template("site_detail.html", site=site,
                           devices=devices_with_status, inspections=inspections)


@app.route("/sites/<int:site_id>/edit", methods=["POST"])
@login_required
def edit_site(site_id):
    f = request.form
    conn = get_conn()
    conn.execute("""
        UPDATE sites SET customer_name=?, site_name=?, address=?, contact_name=?,
            contact_phone=?, contact_email=?, notes=?
        WHERE id=?
    """, (f.get("customer_name", "").strip(), f.get("site_name", "").strip(),
          f.get("address", "").strip(), f.get("contact_name", "").strip(),
          f.get("contact_phone", "").strip(), f.get("contact_email", "").strip(),
          f.get("notes", "").strip(), site_id))
    conn.commit(); conn.close()
    log_event(session["user_id"], "site_edited", "site", site_id,
              f.get("customer_name", "").strip())
    flash("Site updated.", "success")
    return redirect(url_for("site_detail", site_id=site_id))


@app.route("/sites/<int:site_id>/devices/new", methods=["POST"])
@login_required
def new_device(site_id):
    f = request.form
    conn = get_conn()
    conn.execute("""
        INSERT INTO devices (site_id, device_type, barcode, model, serial, location)
        VALUES (?,?,?,?,?,?)
    """, (site_id, f.get("device_type"), f.get("barcode"), f.get("model"),
          f.get("serial"), f.get("location")))
    conn.commit(); conn.close()
    log_event(session["user_id"], "device_added", "site", site_id, f.get("barcode") or f.get("device_type"))
    flash("Device added.", "success")
    return redirect(url_for("site_detail", site_id=site_id))


# ---------- inspections ----------
@app.route("/inspect/new", methods=["GET", "POST"])
@login_required
def new_inspection():
    conn = get_conn()
    sites_rows = conn.execute("SELECT * FROM sites ORDER BY customer_name").fetchall()
    if request.method == "POST":
        site_id = int(request.form["site_id"])
        slug = request.form["template_slug"]
        if slug not in TEMPLATES:
            flash("Unknown template.", "error"); return redirect(url_for("new_inspection"))
        gps_lat = request.form.get("gps_lat") or None
        gps_lng = request.form.get("gps_lng") or None
        device_id = request.form.get("device_id") or None
        cur = conn.execute("""
            INSERT INTO inspections (site_id, inspector_id, template_slug, status, started_at, gps_lat, gps_lng, device_id)
            VALUES (?, ?, ?, 'in_progress', ?, ?, ?, ?)
        """, (site_id, session["user_id"], slug,
              datetime.utcnow().isoformat(timespec="seconds"),
              float(gps_lat) if gps_lat else None,
              float(gps_lng) if gps_lng else None,
              int(device_id) if device_id else None))
        iid = cur.lastrowid
        conn.commit(); conn.close()
        action = "firewatch_started" if slug == "firewatch" else "inspection_started"
        log_event(session["user_id"], action, "inspection", iid, TEMPLATES[slug]["name"])
        return redirect(url_for("inspection", inspection_id=iid))
    conn.close()
    return render_template("new_inspection.html", sites=sites_rows)


@app.route("/inspections/<int:inspection_id>")
@login_required
def inspection(inspection_id):
    conn = get_conn()
    insp = conn.execute("""
        SELECT i.*, s.customer_name, s.site_name, s.address, u.full_name AS inspector_name
        FROM inspections i
        JOIN sites s ON s.id = i.site_id
        JOIN users u ON u.id = i.inspector_id
        WHERE i.id = ?
    """, (inspection_id,)).fetchone()
    if not insp:
        conn.close(); abort(404)
    items = conn.execute(
        "SELECT * FROM inspection_items WHERE inspection_id = ?", (inspection_id,)
    ).fetchall()
    rounds = conn.execute(
        "SELECT * FROM firewatch_rounds WHERE inspection_id = ? ORDER BY round_no DESC",
        (inspection_id,)
    ).fetchall()
    photos = conn.execute(
        "SELECT * FROM inspection_photos WHERE inspection_id = ? ORDER BY uploaded_at DESC",
        (inspection_id,)
    ).fetchall()
    comments = conn.execute("""
        SELECT c.*, u.full_name AS user_name FROM inspection_comments c
        JOIN users u ON u.id = c.user_id
        WHERE c.inspection_id = ? ORDER BY c.created_at ASC
    """, (inspection_id,)).fetchall()
    conn.close()
    answers = {row["item_id"]: dict(row) for row in items}
    template = get_template(insp["template_slug"])
    return render_template("inspection.html", insp=insp, template=template,
                           answers=answers, rounds=rounds, photos=photos, comments=comments)


@app.route("/inspections/<int:inspection_id>/save", methods=["POST"])
@login_required
def save_item(inspection_id):
    """Auto-save endpoint - POSTed on every change."""
    j = request.get_json(silent=True) or {}
    item_id = request.form.get("item_id") or j.get("item_id")
    result = request.form.get("result") if "result" in request.form else j.get("result")
    note   = request.form.get("note")   if "note"   in request.form else j.get("note")
    if not item_id:
        return jsonify({"ok": False, "error": "missing item_id"}), 400
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM inspection_items WHERE inspection_id = ? AND item_id = ?",
        (inspection_id, item_id),
    ).fetchone()
    if existing:
        if result is not None and note is not None:
            conn.execute("UPDATE inspection_items SET result=?, note=? WHERE id=?",
                         (result, note, existing["id"]))
        elif result is not None:
            conn.execute("UPDATE inspection_items SET result=? WHERE id=?",
                         (result, existing["id"]))
        elif note is not None:
            conn.execute("UPDATE inspection_items SET note=? WHERE id=?",
                         (note, existing["id"]))
    else:
        conn.execute("INSERT INTO inspection_items (inspection_id, item_id, result, note) VALUES (?,?,?,?)",
                     (inspection_id, item_id, result, note))
    conn.commit(); conn.close()
    return jsonify({"ok": True, "saved_at": datetime.utcnow().isoformat(timespec="seconds")})


# ---------- firewatch rounds ----------
@app.route("/inspections/<int:inspection_id>/round", methods=["POST"])
@login_required
def add_round(inspection_id):
    conn = get_conn()
    last = conn.execute(
        "SELECT MAX(round_no) AS m FROM firewatch_rounds WHERE inspection_id = ?",
        (inspection_id,)).fetchone()
    next_no = (last["m"] or 0) + 1
    f = request.form
    gps_lat = f.get("gps_lat") or None
    gps_lng = f.get("gps_lng") or None
    conn.execute("""
        INSERT INTO firewatch_rounds (inspection_id, round_no, started_at, location, observations, all_clear, gps_lat, gps_lng)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (inspection_id, next_no,
          datetime.utcnow().isoformat(timespec="seconds"),
          f.get("location", "").strip(),
          f.get("observations", "").strip(),
          1 if f.get("all_clear") in ("1", "on", "yes") else 0,
          float(gps_lat) if gps_lat else None,
          float(gps_lng) if gps_lng else None))
    conn.commit(); conn.close()
    log_event(session["user_id"], "round_logged", "inspection", inspection_id, f"Round #{next_no}")
    flash(f"Round #{next_no} logged.", "success")
    return redirect(url_for("inspection", inspection_id=inspection_id))


# ---------- comments / chat ----------
@app.route("/inspections/<int:inspection_id>/comment", methods=["POST"])
@login_required
def add_comment(inspection_id):
    body = (request.form.get("body") or "").strip()
    if not body:
        flash("Empty comment.", "error")
        return redirect(url_for("inspection", inspection_id=inspection_id))
    conn = get_conn()
    conn.execute("""
        INSERT INTO inspection_comments (inspection_id, user_id, body, created_at)
        VALUES (?, ?, ?, ?)
    """, (inspection_id, session["user_id"], body,
          datetime.utcnow().isoformat(timespec="seconds")))
    conn.commit(); conn.close()
    log_event(session["user_id"], "comment", "inspection", inspection_id, body[:80])
    return redirect(url_for("inspection", inspection_id=inspection_id) + "#comments")


# ---------- photo upload ----------
ALLOWED_EXT = {"jpg", "jpeg", "png", "gif", "webp", "heic", "heif"}


@app.route("/inspections/<int:inspection_id>/photo", methods=["POST"])
@login_required
def upload_photo(inspection_id):
    f = request.files.get("photo")
    if not f or not f.filename:
        flash("No file selected.", "error")
        return redirect(url_for("inspection", inspection_id=inspection_id))
    ext = f.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        flash("Unsupported file type.", "error")
        return redirect(url_for("inspection", inspection_id=inspection_id))
    folder = os.path.join(UPLOAD_DIR, str(inspection_id))
    os.makedirs(folder, exist_ok=True)
    fname = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}_{secure_filename(f.filename)}"
    f.save(os.path.join(folder, fname))
    conn = get_conn()
    conn.execute("""
        INSERT INTO inspection_photos (inspection_id, item_id, filename, caption, uploaded_at)
        VALUES (?, ?, ?, ?, ?)
    """, (inspection_id, request.form.get("item_id") or None,
          fname, request.form.get("caption", "").strip(),
          datetime.utcnow().isoformat(timespec="seconds")))
    conn.commit(); conn.close()
    log_event(session["user_id"], "photo_uploaded", "inspection", inspection_id, fname)
    flash("Photo added.", "success")
    return redirect(url_for("inspection", inspection_id=inspection_id) + "#photos")


# ---------- signatures (canvas data URL) ----------
@app.route("/inspections/<int:inspection_id>/signature", methods=["POST"])
@login_required
def save_signature(inspection_id):
    who = request.form.get("who")  # 'inspector' or 'customer'
    data_url = request.form.get("data_url", "")
    if who not in ("inspector", "customer") or not data_url.startswith("data:image"):
        return jsonify({"ok": False}), 400
    col = "inspector_signature" if who == "inspector" else "customer_signature"
    conn = get_conn()
    conn.execute(f"UPDATE inspections SET {col} = ? WHERE id = ?", (data_url, inspection_id))
    conn.commit(); conn.close()
    return jsonify({"ok": True})


# ---------- API: sites list for JS dropdowns ----------
@app.route("/api/sites")
@login_required
def api_sites():
    conn = get_conn()
    rows = conn.execute("SELECT id, customer_name, site_name FROM sites ORDER BY customer_name").fetchall()
    conn.close()
    return jsonify([{"id": r["id"], "label": f"{r['customer_name']} — {r['site_name']}"} for r in rows])


# ---------- barcode lookup ----------
@app.route("/api/lookup_barcode")
@login_required
def lookup_barcode():
    code = (request.args.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "missing code"}), 400
    conn = get_conn()
    d = conn.execute("""
        SELECT d.*, s.customer_name, s.site_name FROM devices d
        JOIN sites s ON s.id = d.site_id
        WHERE d.barcode = ? OR d.serial = ?
    """, (code, code)).fetchone()
    conn.close()
    if not d:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "device": dict(d)})


@app.route("/api/devices/<int:device_id>/summary")
@login_required
def device_summary(device_id):
    """Lightweight JSON summary used by the camera-scan flow on inspection pages.

    Inspector scans a /d/<id> QR -> the scanner resolves it here and fills the
    barcode input on the active inspection so the lookup banner matches.
    """
    conn = get_conn()
    d = conn.execute("""
        SELECT d.id, d.barcode, d.serial, d.device_type, d.model, d.location,
               d.extinguisher_type, d.extinguisher_size,
               s.customer_name, s.site_name
        FROM devices d JOIN sites s ON s.id = d.site_id
        WHERE d.id = ?
    """, (device_id,)).fetchone()
    conn.close()
    if not d:
        return jsonify({"ok": False, "error": "not found"}), 404
    out = dict(d)
    out["ok"] = True
    return jsonify(out)


# ---------- complete + report ----------
@app.route("/inspections/<int:inspection_id>/complete", methods=["POST"])
@login_required
def complete_inspection(inspection_id):
    f = request.form
    conn = get_conn()
    # Don't overwrite drawn signatures (data URLs) with empty strings.
    # Newly completed inspections go to approval_status='pending' — they are NOT
    # visible to clients/portals until an admin approves them.
    sets = ["status='completed'", "completed_at=?", "customer_email=?", "notes=?",
            "approval_status='pending'", "approved_by=NULL", "approved_at=NULL",
            "rejection_reason=NULL"]
    vals = [datetime.utcnow().isoformat(timespec="seconds"),
            f.get("customer_email", "").strip(),
            f.get("notes", "").strip()]
    if f.get("inspector_signature"):
        sets.append("inspector_signature=?"); vals.append(f.get("inspector_signature").strip())
    if f.get("customer_signature"):
        sets.append("customer_signature=?"); vals.append(f.get("customer_signature").strip())
    vals.append(inspection_id)
    conn.execute(f"UPDATE inspections SET {', '.join(sets)} WHERE id = ?", vals)

    insp = conn.execute("SELECT site_id, template_slug FROM inspections WHERE id = ?",
                        (inspection_id,)).fetchone()
    if insp:
        slug = insp["template_slug"]
        months = TEMPLATES[slug].get("frequency_months") or 0
        if months:
            next_due = (datetime.utcnow().date() + timedelta(days=months * 30)).isoformat()
            device_type_map = {
                "fire_extinguisher": "extinguisher",
                "fire_alarm": "fire_alarm_panel",
                "kitchen_suppression": "kitchen_suppression",
                "emergency_lighting": "emergency_light",
            }
            dt = device_type_map.get(slug)
            if dt:
                conn.execute("""
                    UPDATE devices SET last_inspected = ?, next_due = ?
                    WHERE site_id = ? AND device_type = ?
                """, (datetime.utcnow().date().isoformat(), next_due, insp["site_id"], dt))
    # Advance site schedule next_due date
    if insp:
        sched = conn.execute("""
            SELECT id, frequency_months FROM site_schedules
            WHERE site_id=? AND template_slug=?
        """, (insp["site_id"], insp["template_slug"])).fetchone()
        if sched:
            next_due = (datetime.utcnow().date() + timedelta(days=sched["frequency_months"] * 30)).isoformat()
            conn.execute("UPDATE site_schedules SET next_due=? WHERE id=?", (next_due, sched["id"]))
    conn.commit(); conn.close()
    log_event(session["user_id"], "inspection_completed", "inspection", inspection_id)
    flash("Inspection completed and report ready.", "success")
    return redirect(url_for("report", inspection_id=inspection_id))


@app.route("/inspections/<int:inspection_id>/report")
@login_required
def report(inspection_id):
    conn = get_conn()
    insp = conn.execute("""
        SELECT i.*, s.customer_name, s.site_name, s.address, s.contact_name, s.contact_phone,
               u.full_name AS inspector_name
        FROM inspections i
        JOIN sites s ON s.id = i.site_id
        JOIN users u ON u.id = i.inspector_id
        WHERE i.id = ?
    """, (inspection_id,)).fetchone()
    if not insp:
        conn.close(); abort(404)
    items = conn.execute(
        "SELECT * FROM inspection_items WHERE inspection_id = ?", (inspection_id,)
    ).fetchall()
    rounds = conn.execute(
        "SELECT * FROM firewatch_rounds WHERE inspection_id = ? ORDER BY round_no ASC",
        (inspection_id,)
    ).fetchall()
    photos = conn.execute(
        "SELECT * FROM inspection_photos WHERE inspection_id = ? ORDER BY uploaded_at ASC",
        (inspection_id,)
    ).fetchall()
    conn.close()
    answers = {row["item_id"]: dict(row) for row in items}
    template = get_template(insp["template_slug"])

    counts = {"pass": 0, "fail": 0, "na": 0, "unanswered": 0}
    for item in all_items(insp["template_slug"]):
        if item["type"] != "check": continue
        ans = answers.get(item["id"])
        if not ans or not ans.get("result"):
            counts["unanswered"] += 1
        else:
            counts[ans["result"]] = counts.get(ans["result"], 0) + 1

    # Build a mailto URL for "Email this report"
    base_url = request.url_root.rstrip("/")
    report_url = base_url + url_for("report", inspection_id=inspection_id)
    subject = f"IGH Inspection Report - {insp['customer_name']} - {template['name']}"
    body = (f"Hi {insp['contact_name'] or 'team'},%0D%0A%0D%0A"
            f"Your IGH inspection is complete. Summary:%0D%0A"
            f"  Pass: {counts['pass']}  Fail: {counts['fail']}  N/A: {counts['na']}%0D%0A%0D%0A"
            f"Full report: {report_url}%0D%0A%0D%0A"
            f"Thanks,%0D%0A{insp['inspector_name']}%0D%0AIGH Health, Fire & Safety")
    mailto = f"mailto:{quote(insp['customer_email'] or '')}?subject={quote(subject)}&body={body}"

    # Pull every extinguisher at this site so the report can list them with status
    conn2 = get_conn()
    site_devices = conn2.execute(
        "SELECT * FROM devices WHERE site_id = ? AND device_type = 'extinguisher' ORDER BY location",
        (insp["site_id"],)
    ).fetchall()
    report_deficiencies = conn2.execute("""
        SELECT * FROM deficiencies WHERE inspection_id = ? ORDER BY severity, created_at
    """, (inspection_id,)).fetchall()
    conn2.close()
    extinguishers = []
    for sd in site_devices:
        sdd = dict(sd)
        st, msg = expiration_status(sdd)
        sdd["exp_status"] = st
        sdd["exp_msg"] = msg
        extinguishers.append(sdd)

    return render_template("report.html", insp=insp, template=template,
                           answers=answers, counts=counts, rounds=rounds, photos=photos,
                           mailto=mailto, company=COMPANY,
                           occupancy="Commercial", patrol_interval="15 minutes",
                           extinguishers=extinguishers,
                           report_deficiencies=report_deficiencies)


@app.route("/reports")
@login_required
def reports():
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.*, s.customer_name, s.site_name, u.full_name AS inspector_name
        FROM inspections i
        JOIN sites s ON s.id = i.site_id
        JOIN users u ON u.id = i.inspector_id
        WHERE i.status = 'completed'
        ORDER BY i.completed_at DESC
    """).fetchall()
    conn.close()
    return render_template("reports.html", inspections=rows)


# ---------- admin: approval queue ----------
@app.route("/admin/approvals")
@login_required
@admin_required
def admin_approvals():
    """Pending-state approval queue. Lists completed inspections awaiting admin sign-off.

    Per system requirements, no client-visible data is exposed until an admin
    approves the inspection (and its deficiencies)."""
    conn = get_conn()
    pending = conn.execute("""
        SELECT i.*, s.customer_name, s.site_name, u.full_name AS inspector_name,
               (SELECT COUNT(*) FROM deficiencies WHERE inspection_id = i.id) AS def_count
        FROM inspections i
        JOIN sites s ON s.id = i.site_id
        JOIN users u ON u.id = i.inspector_id
        WHERE i.status = 'completed' AND i.approval_status = 'pending'
        ORDER BY i.completed_at ASC
    """).fetchall()
    recently_approved = conn.execute("""
        SELECT i.*, s.customer_name, s.site_name, u.full_name AS inspector_name,
               a.full_name AS approver_name
        FROM inspections i
        JOIN sites s ON s.id = i.site_id
        JOIN users u ON u.id = i.inspector_id
        LEFT JOIN users a ON a.id = i.approved_by
        WHERE i.approval_status = 'approved'
        ORDER BY i.approved_at DESC LIMIT 10
    """).fetchall()
    rejected = conn.execute("""
        SELECT i.*, s.customer_name, s.site_name, u.full_name AS inspector_name
        FROM inspections i
        JOIN sites s ON s.id = i.site_id
        JOIN users u ON u.id = i.inspector_id
        WHERE i.approval_status = 'rejected'
        ORDER BY i.completed_at DESC LIMIT 10
    """).fetchall()
    conn.close()
    return render_template("admin_approvals.html",
                           pending=pending, recently_approved=recently_approved,
                           rejected=rejected)


@app.route("/admin/inspections/<int:inspection_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_inspection(inspection_id):
    """Admin approves an inspection. Cascades approval to its deficiencies so
    they become visible in the customer portal at the same time. Audit-logged."""
    conn = get_conn()
    insp = conn.execute(
        "SELECT id, approval_status FROM inspections WHERE id = ?",
        (inspection_id,)
    ).fetchone()
    if not insp:
        conn.close(); abort(404)
    prev = insp["approval_status"]
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn.execute(
        """UPDATE inspections
           SET approval_status='approved', approved_by=?, approved_at=?,
               rejection_reason=NULL
           WHERE id=?""",
        (session["user_id"], now, inspection_id)
    )
    # Cascade to deficiencies attached to this inspection
    conn.execute(
        "UPDATE deficiencies SET approval_status='approved' WHERE inspection_id=?",
        (inspection_id,)
    )
    conn.commit(); conn.close()
    log_event(session["user_id"], "inspection_approved", "inspection", inspection_id,
              f"{prev} -> approved")
    flash("Inspection approved. Customer portal will now show this report.", "success")
    return redirect(request.referrer or url_for("admin_approvals"))


@app.route("/admin/inspections/<int:inspection_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_inspection(inspection_id):
    """Admin rejects an inspection. The rejection_reason is preserved so the
    inspector can revise and resubmit. Stays invisible to clients. Audit-logged."""
    reason = (request.form.get("rejection_reason") or "").strip()
    if not reason:
        flash("A rejection reason is required so the inspector knows what to fix.", "error")
        return redirect(request.referrer or url_for("admin_approvals"))
    conn = get_conn()
    insp = conn.execute(
        "SELECT id, approval_status FROM inspections WHERE id = ?",
        (inspection_id,)
    ).fetchone()
    if not insp:
        conn.close(); abort(404)
    prev = insp["approval_status"]
    conn.execute(
        """UPDATE inspections
           SET approval_status='rejected', rejection_reason=?,
               approved_by=NULL, approved_at=NULL
           WHERE id=?""",
        (reason, inspection_id)
    )
    conn.commit(); conn.close()
    log_event(session["user_id"], "inspection_rejected", "inspection", inspection_id,
              f"{prev} -> rejected: {reason[:80]}")
    flash("Inspection sent back to the inspector with feedback.", "success")
    return redirect(request.referrer or url_for("admin_approvals"))


@app.route("/inspections/<int:inspection_id>/resubmit", methods=["POST"])
@login_required
def resubmit_inspection(inspection_id):
    """Inspector resubmits a rejected inspection. Resets state to pending."""
    conn = get_conn()
    insp = conn.execute(
        "SELECT id, inspector_id, approval_status FROM inspections WHERE id = ?",
        (inspection_id,)
    ).fetchone()
    if not insp:
        conn.close(); abort(404)
    if insp["inspector_id"] != session["user_id"] and session.get("user_role") != "admin":
        conn.close(); abort(403)
    if insp["approval_status"] != "rejected":
        conn.close()
        flash("Only rejected inspections can be resubmitted.", "error")
        return redirect(url_for("inspection", inspection_id=inspection_id))
    conn.execute(
        """UPDATE inspections
           SET approval_status='pending', rejection_reason=NULL
           WHERE id=?""",
        (inspection_id,)
    )
    conn.commit(); conn.close()
    log_event(session["user_id"], "inspection_resubmitted", "inspection", inspection_id,
              "rejected -> pending")
    flash("Inspection resubmitted for admin review.", "success")
    return redirect(url_for("inspection", inspection_id=inspection_id))


# ---------- profile / "More" tab ----------
@app.route("/profile")
@login_required
def profile():
    """The 'More' tab — user profile + quick links to inspector tools + admin menu."""
    conn = get_conn()
    open_defs = conn.execute(
        "SELECT COUNT(*) FROM deficiencies WHERE status='open'"
    ).fetchone()[0]
    pending_approvals = 0
    if session.get("user_role") == "admin":
        pending_approvals = conn.execute(
            "SELECT COUNT(*) FROM inspections WHERE status='completed' AND approval_status='pending'"
        ).fetchone()[0]
    conn.close()
    return render_template("profile.html",
                           open_defs=open_defs,
                           pending_approvals=pending_approvals)


# ---------- admin: template editor + activity log ----------
@app.route("/admin/templates", methods=["GET", "POST"])
@login_required
@admin_required
def admin_templates():
    error = None
    if request.method == "POST":
        slug = request.form.get("slug", "").strip()
        body = request.form.get("body", "").strip()
        slug = re.sub(r"[^a-z0-9_]", "_", slug.lower())
        if not slug:
            error = "Slug required."
        else:
            try:
                parsed = json.loads(body)
                assert isinstance(parsed, dict) and "name" in parsed and "sections" in parsed
                TEMPLATES[slug] = parsed
                save_overrides()
                log_event(session["user_id"], "template_edited", "template", None, slug)
                flash(f"Template '{slug}' saved.", "success")
                return redirect(url_for("admin_templates"))
            except Exception as e:
                error = f"Invalid JSON: {e}"
    return render_template("admin_templates.html", templates=TEMPLATES, error=error)


@app.route("/admin/templates/<slug>/delete", methods=["POST"])
@login_required
@admin_required
def admin_template_delete(slug):
    if slug in TEMPLATES:
        TEMPLATES.pop(slug)
        save_overrides()
        log_event(session["user_id"], "template_deleted", "template", None, slug)
        flash(f"Template '{slug}' removed.", "success")
    return redirect(url_for("admin_templates"))


@app.route("/admin/events")
@login_required
@admin_required
def admin_events():
    conn = get_conn()
    rows = conn.execute("""
        SELECT e.*, u.full_name AS user_name FROM events e
        LEFT JOIN users u ON u.id = e.user_id
        ORDER BY e.created_at DESC LIMIT 200
    """).fetchall()
    conn.close()
    return render_template("admin_events.html", events=rows)


# ---------- email via Resend ----------
from mailer import send_report_email


@app.route("/inspections/<int:inspection_id>/email", methods=["POST"])
@login_required
def email_report(inspection_id):
    """Send the report to the customer via Resend."""
    conn = get_conn()
    insp = conn.execute("""
        SELECT i.*, s.customer_name, s.site_name, s.contact_name,
               u.full_name AS inspector_name
        FROM inspections i
        JOIN sites s ON s.id = i.site_id
        JOIN users u ON u.id = i.inspector_id
        WHERE i.id = ?
    """, (inspection_id,)).fetchone()
    conn.close()
    if not insp:
        abort(404)
    to = request.form.get("to") or insp["customer_email"]
    if not to:
        flash("No customer email on file.", "error")
        return redirect(url_for("report", inspection_id=inspection_id))
    template = get_template(insp["template_slug"])
    report_url = request.url_root.rstrip("/") + url_for("report", inspection_id=inspection_id)
    html = render_template("email_report.html", insp=insp, template=template, report_url=report_url)
    ok, info = send_report_email(
        to,
        f"IGH Inspection Report - {insp['customer_name']} - {template['name']}",
        html,
    )
    if ok:
        log_event(session["user_id"], "report_emailed", "inspection", inspection_id, to)
        flash(f"Report emailed to {to}.", "success")
    else:
        flash(f"Email failed: {info}", "error")
    return redirect(url_for("report", inspection_id=inspection_id))


# ---------- devices, QR codes, expiration tracking ----------
def years_since(iso_date):
    """Return float years since the given ISO date string, or None."""
    if not iso_date:
        return None
    try:
        d = datetime.fromisoformat(iso_date).date()
        days = (datetime.utcnow().date() - d).days
        return round(days / 365.25, 1)
    except Exception:
        return None


def expiration_status(device):
    """Return ('ok'|'due-soon'|'overdue', message) for a device based on 7-yr rule."""
    if not device:
        return ("ok", "")
    if device.get("device_type") != "extinguisher":
        return ("ok", "")
    yrs = years_since(device.get("manufactured_date"))
    if yrs is None:
        return ("unknown", "Manufacture date not recorded")
    if yrs >= 7:
        return ("overdue", f"Hydrostatic test OVERDUE ({yrs} yrs since manufacture)")
    if yrs >= 6:
        return ("due-soon", f"Hydrostatic test due soon ({yrs} yrs since manufacture)")
    return ("ok", f"{yrs} yrs since manufacture")


@app.template_filter("years_since")
def _years_since_filter(iso):
    y = years_since(iso)
    return f"{y} yrs" if y is not None else "-"


@app.route("/devices/<int:device_id>")
@login_required
def device_detail(device_id):
    conn = get_conn()
    d = conn.execute("""
        SELECT d.*, s.customer_name, s.site_name, s.address
        FROM devices d JOIN sites s ON s.id = d.site_id
        WHERE d.id = ?
    """, (device_id,)).fetchone()
    if not d:
        conn.close(); abort(404)
    history = conn.execute("""
        SELECT i.*, u.full_name AS inspector_name
        FROM inspections i
        LEFT JOIN users u ON u.id = i.inspector_id
        WHERE i.device_id = ? OR (i.site_id = ? AND i.template_slug = 'fire_extinguisher')
        ORDER BY i.started_at DESC LIMIT 20
    """, (device_id, d["site_id"])).fetchall()
    photos = conn.execute(
        "SELECT * FROM inspection_photos WHERE device_id = ? ORDER BY uploaded_at DESC",
        (device_id,)
    ).fetchall()
    conn.close()
    status, msg = expiration_status(dict(d))
    return render_template("device_detail.html", device=d, history=history,
                           photos=photos, status=status, status_msg=msg)


@app.route("/qr/<token>")
def device_by_qr(token):
    """Public QR-scan landing (token-based, legacy printed labels).

    Looks up the device by random token then routes to the device record.
    Unauthenticated users are bounced to login first so the record stays gated.
    """
    conn = get_conn()
    d = conn.execute("SELECT id FROM devices WHERE qr_token = ?", (token,)).fetchone()
    conn.close()
    if not d:
        abort(404)
    if "user_id" not in session:
        return redirect(url_for("login", next=url_for("device_detail", device_id=d["id"])))
    return redirect(url_for("device_detail", device_id=d["id"]))


@app.route("/d/<int:device_id>")
def device_short(device_id):
    """Short URL for QR codes — /d/123 → device detail (auth-gated).

    Used as the payload for newly generated QR codes (shorter than /qr/<token>,
    which keeps the printed QR denser and easier for phone cameras to lock onto).
    """
    conn = get_conn()
    d = conn.execute("SELECT id FROM devices WHERE id = ?", (device_id,)).fetchone()
    conn.close()
    if not d:
        abort(404)
    if "user_id" not in session:
        return redirect(url_for("login", next=url_for("device_detail", device_id=device_id)))
    return redirect(url_for("device_detail", device_id=device_id))


@app.route("/devices/<int:device_id>/qr.png")
@login_required
def device_qr_png(device_id):
    """Render a PNG QR code that encodes the device's short URL (/d/<id>).

    Falls back to /qr/<token> when the legacy token is present, so labels
    that were already printed continue to resolve.
    """
    conn = get_conn()
    d = conn.execute("SELECT id, qr_token FROM devices WHERE id = ?", (device_id,)).fetchone()
    conn.close()
    if not d:
        abort(404)
    base_url = request.url_root.rstrip("/")
    # Prefer the short, stable /d/<id> URL for new labels.
    target = f"{base_url}/d/{d['id']}"
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(target)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#13334A", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    from flask import send_file
    return send_file(buf, mimetype="image/png", download_name=f"qr_{device_id}.png")


@app.route("/devices/<int:device_id>/label")
@login_required
def device_qr_label(device_id):
    """Printable QR label page (~2"x1"), browser-printed via window.print()."""
    conn = get_conn()
    d = conn.execute("""
        SELECT d.*, s.customer_name, s.site_name
        FROM devices d JOIN sites s ON s.id = d.site_id
        WHERE d.id = ?
    """, (device_id,)).fetchone()
    conn.close()
    if not d:
        abort(404)
    return render_template("qr_label.html", device=d)


@app.route("/devices/<int:device_id>/edit", methods=["POST"])
@login_required
def edit_device(device_id):
    f = request.form
    conn = get_conn()
    conn.execute("""
        UPDATE devices SET
            extinguisher_type = ?, extinguisher_size = ?,
            manufactured_date = ?, last_service_date = ?,
            location = ?, model = ?, serial = ?, barcode = ?, notes = ?
        WHERE id = ?
    """, (f.get("extinguisher_type"), f.get("extinguisher_size"),
          f.get("manufactured_date") or None, f.get("last_service_date") or None,
          f.get("location"), f.get("model"), f.get("serial"),
          f.get("barcode"), f.get("notes"), device_id))
    # Make sure it has a QR token
    row = conn.execute("SELECT qr_token FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row["qr_token"]:
        conn.execute("UPDATE devices SET qr_token=? WHERE id=?",
                     (secrets.token_urlsafe(12), device_id))
    conn.commit()
    conn.close()
    log_event(session["user_id"], "device_edited", "device", device_id)
    flash("Device updated.", "success")
    return redirect(url_for("device_detail", device_id=device_id))


@app.route("/devices/<int:device_id>/regen-qr", methods=["POST"])
@login_required
def regen_qr(device_id):
    conn = get_conn()
    conn.execute("UPDATE devices SET qr_token=? WHERE id=?",
                 (secrets.token_urlsafe(12), device_id))
    conn.commit()
    conn.close()
    log_event(session["user_id"], "qr_regenerated", "device", device_id)
    flash("QR code regenerated.", "success")
    return redirect(url_for("device_detail", device_id=device_id))


# ---------- PWA ----------
@app.route("/manifest.webmanifest")
def manifest():
    return send_from_directory("static", "manifest.webmanifest", mimetype="application/manifest+json")


@app.route("/sw.js")
def sw():
    return send_from_directory("static", "sw.js", mimetype="application/javascript")


@app.route("/static/uploads/<int:inspection_id>/<path:filename>")
def uploaded_file(inspection_id, filename):
    return send_from_directory(os.path.join(UPLOAD_DIR, str(inspection_id)), filename)


# ---------- admin: user management ----------
@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    conn = get_conn()
    users = conn.execute("SELECT * FROM users ORDER BY full_name").fetchall()
    conn.close()
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/new", methods=["GET", "POST"])
@login_required
@admin_required
def admin_user_new():
    from werkzeug.security import generate_password_hash
    error = None
    if request.method == "POST":
        f = request.form
        username = f.get("username", "").strip().lower()
        full_name = f.get("full_name", "").strip()
        password = f.get("password", "")
        role = f.get("role", "inspector")
        if not username or not full_name or not password:
            error = "All fields required."
        else:
            try:
                conn = get_conn()
                conn.execute(
                    "INSERT INTO users (username, password_hash, full_name, role) VALUES (?,?,?,?)",
                    (username, generate_password_hash(password), full_name, role)
                )
                conn.commit(); conn.close()
                log_event(session["user_id"], "user_created", "user", None, full_name)
                flash(f"User {full_name} created.", "success")
                return redirect(url_for("admin_users"))
            except Exception as e:
                error = f"Username already taken or error: {e}"
    return render_template("admin_user_form.html", error=error, user=None)


@app.route("/admin/users/<int:uid>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_user_edit(uid):
    from werkzeug.security import generate_password_hash
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    if not user:
        abort(404)
    error = None
    if request.method == "POST":
        f = request.form
        full_name = f.get("full_name", "").strip()
        role = f.get("role", "inspector")
        active = 1 if f.get("active") else 0
        new_pw = f.get("password", "").strip()
        conn = get_conn()
        if new_pw:
            conn.execute("UPDATE users SET full_name=?, role=?, active=?, password_hash=? WHERE id=?",
                         (full_name, role, active, generate_password_hash(new_pw), uid))
        else:
            conn.execute("UPDATE users SET full_name=?, role=?, active=? WHERE id=?",
                         (full_name, role, active, uid))
        conn.commit(); conn.close()
        log_event(session["user_id"], "user_edited", "user", uid, full_name)
        flash("User updated.", "success")
        return redirect(url_for("admin_users"))
    return render_template("admin_user_form.html", error=error, user=dict(user))


# ---------- deficiencies ----------
@app.route("/deficiencies")
@login_required
def deficiencies_list():
    conn = get_conn()
    status_filter = request.args.get("status", "open")
    if status_filter == "all":
        rows = conn.execute("""
            SELECT d.*, s.customer_name, s.site_name, u.full_name AS creator_name,
                   i.template_slug
            FROM deficiencies d
            JOIN sites s ON s.id = d.site_id
            LEFT JOIN users u ON u.id = d.created_by
            LEFT JOIN inspections i ON i.id = d.inspection_id
            ORDER BY d.created_at DESC
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT d.*, s.customer_name, s.site_name, u.full_name AS creator_name,
                   i.template_slug
            FROM deficiencies d
            JOIN sites s ON s.id = d.site_id
            LEFT JOIN users u ON u.id = d.created_by
            LEFT JOIN inspections i ON i.id = d.inspection_id
            WHERE d.status = ?
            ORDER BY CASE d.severity WHEN 'critical' THEN 1 WHEN 'major' THEN 2 ELSE 3 END,
                     d.created_at DESC
        """, (status_filter,)).fetchall()
    conn.close()
    return render_template("admin_deficiencies.html", deficiencies=rows, status_filter=status_filter)


@app.route("/inspections/<int:inspection_id>/deficiencies/new", methods=["GET", "POST"])
@login_required
def new_deficiency(inspection_id):
    conn = get_conn()
    insp = conn.execute("""
        SELECT i.*, s.customer_name, s.site_name, s.contact_email
        FROM inspections i JOIN sites s ON s.id = i.site_id
        WHERE i.id = ?
    """, (inspection_id,)).fetchone()
    if not insp:
        conn.close(); abort(404)
    if request.method == "POST":
        f = request.form
        desc = f.get("description", "").strip()
        if not desc:
            conn.close()
            flash("Description required.", "error")
            return redirect(request.url)
        item_id = f.get("item_id", "").strip() or None
        item_label = f.get("item_label", "").strip() or None
        severity = f.get("severity", "major")
        assigned_to = f.get("assigned_to", "").strip() or None
        due_date = f.get("due_date", "").strip() or None
        cur = conn.execute("""
            INSERT INTO deficiencies (inspection_id, site_id, item_id, item_label, description,
                severity, status, assigned_to, due_date, created_by, created_at)
            VALUES (?,?,?,?,?,?,'open',?,?,?,?)
        """, (inspection_id, insp["site_id"], item_id, item_label, desc,
              severity, assigned_to, due_date, session["user_id"],
              datetime.utcnow().isoformat(timespec="seconds")))
        def_id = cur.lastrowid
        conn.commit()
        log_event(session["user_id"], "deficiency_created", "inspection", inspection_id,
                  f"{severity}: {desc[:60]}")
        # Email site contact if they have an email
        contact_email = insp["contact_email"]
        if contact_email:
            from mailer import send_report_email
            html = render_template("email_deficiency.html", insp=insp, desc=desc,
                                   severity=severity, due_date=due_date)
            send_report_email(contact_email,
                              f"IGH Deficiency Notice - {insp['customer_name']}",
                              html)
        conn.close()
        flash("Deficiency recorded.", "success")
        return redirect(url_for("inspection", inspection_id=inspection_id))
    item_id = request.args.get("item_id", "")
    item_label = request.args.get("item_label", "")
    conn.close()
    return render_template("deficiency_form.html", insp=dict(insp), item_id=item_id,
                           item_label=item_label)


@app.route("/deficiencies/<int:def_id>/resolve", methods=["POST"])
@login_required
def resolve_deficiency(def_id):
    notes = request.form.get("resolution_notes", "").strip()
    conn = get_conn()
    d = conn.execute("SELECT * FROM deficiencies WHERE id=?", (def_id,)).fetchone()
    if not d:
        conn.close(); abort(404)
    conn.execute("""
        UPDATE deficiencies SET status='resolved', resolution_notes=?, resolved_at=? WHERE id=?
    """, (notes, datetime.utcnow().isoformat(timespec="seconds"), def_id))
    conn.commit(); conn.close()
    log_event(session["user_id"], "deficiency_resolved", "inspection", d["inspection_id"],
              f"#{def_id}")
    flash("Deficiency marked resolved.", "success")
    return redirect(request.referrer or url_for("deficiencies_list"))


@app.route("/deficiencies/<int:def_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_deficiency(def_id):
    conn = get_conn()
    conn.execute("DELETE FROM deficiencies WHERE id=?", (def_id,))
    conn.commit(); conn.close()
    flash("Deficiency deleted.", "success")
    return redirect(url_for("deficiencies_list"))


# ---------- inspection schedules ----------
@app.route("/admin/schedules")
@login_required
@admin_required
def admin_schedules():
    conn = get_conn()
    rows = conn.execute("""
        SELECT ss.*, s.customer_name, s.site_name
        FROM site_schedules ss JOIN sites s ON s.id = ss.site_id
        ORDER BY ss.next_due ASC
    """).fetchall()
    sites_rows = conn.execute("SELECT id, customer_name, site_name FROM sites ORDER BY customer_name").fetchall()
    conn.close()
    return render_template("admin_schedules.html", schedules=rows, sites=sites_rows,
                           TEMPLATES=TEMPLATES)


@app.route("/admin/schedules/new", methods=["POST"])
@login_required
@admin_required
def admin_schedule_new():
    f = request.form
    site_id = int(f.get("site_id"))
    slug = f.get("template_slug")
    freq = int(f.get("frequency_months", 12))
    next_due = f.get("next_due") or None
    notes = f.get("notes", "").strip() or None
    conn = get_conn()
    conn.execute("""
        INSERT INTO site_schedules (site_id, template_slug, frequency_months, next_due, notes, created_at)
        VALUES (?,?,?,?,?,?)
    """, (site_id, slug, freq, next_due, notes,
          datetime.utcnow().isoformat(timespec="seconds")))
    conn.commit(); conn.close()
    flash("Schedule added.", "success")
    return redirect(url_for("admin_schedules"))


@app.route("/admin/schedules/<int:sched_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_schedule_delete(sched_id):
    conn = get_conn()
    conn.execute("DELETE FROM site_schedules WHERE id=?", (sched_id,))
    conn.commit(); conn.close()
    flash("Schedule removed.", "success")
    return redirect(url_for("admin_schedules"))


# ---------- customer portal ----------
@app.route("/portal/<token>")
def customer_portal(token):
    """Public customer portal.

    APPROVAL GATE: Only APPROVED inspections and their deficiencies are visible.
    Pending and rejected work is never exposed to the client side.
    """
    conn = get_conn()
    site = conn.execute("SELECT * FROM sites WHERE portal_token=?", (token,)).fetchone()
    if not site:
        conn.close(); abort(404)
    inspections = conn.execute("""
        SELECT i.*, u.full_name AS inspector_name
        FROM inspections i JOIN users u ON u.id = i.inspector_id
        WHERE i.site_id = ? AND i.status = 'completed'
              AND i.approval_status = 'approved'
        ORDER BY i.completed_at DESC
    """, (site["id"],)).fetchall()
    # Deficiencies are also approval-gated. We only show those tied to an
    # approved inspection (or with their own approval_status='approved').
    deficiencies = conn.execute("""
        SELECT d.* FROM deficiencies d
        LEFT JOIN inspections i ON i.id = d.inspection_id
        WHERE d.site_id = ?
              AND d.approval_status = 'approved'
              AND (i.approval_status IS NULL OR i.approval_status = 'approved')
        ORDER BY d.created_at DESC
    """, (site["id"],)).fetchall()
    conn.close()
    return render_template("portal.html", site=site, inspections=inspections,
                           deficiencies=deficiencies, TEMPLATES=TEMPLATES)


@app.route("/sites/<int:site_id>/portal-token", methods=["POST"])
@login_required
@admin_required
def regen_portal_token(site_id):
    token = secrets.token_urlsafe(16)
    conn = get_conn()
    conn.execute("UPDATE sites SET portal_token=? WHERE id=?", (token, site_id))
    conn.commit(); conn.close()
    flash("Portal link generated.", "success")
    return redirect(url_for("site_detail", site_id=site_id))


# ---------- CSV exports ----------
@app.route("/admin/export/sites.csv")
@login_required
@admin_required
def export_sites_csv():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM sites ORDER BY customer_name").fetchall()
    conn.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id","customer_name","site_name","address","contact_name",
                "contact_phone","contact_email","notes","created_at"])
    for r in rows:
        w.writerow([r["id"], r["customer_name"], r["site_name"], r["address"],
                    r["contact_name"], r["contact_phone"], r["contact_email"],
                    r["notes"], r["created_at"]])
    from flask import Response
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=sites.csv"})


@app.route("/admin/export/inspections.csv")
@login_required
@admin_required
def export_inspections_csv():
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.id, s.customer_name, s.site_name, i.template_slug, i.status,
               u.full_name AS inspector, i.started_at, i.completed_at
        FROM inspections i
        JOIN sites s ON s.id = i.site_id
        JOIN users u ON u.id = i.inspector_id
        ORDER BY i.started_at DESC
    """).fetchall()
    conn.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id","customer","site","template","status","inspector",
                "started_at","completed_at"])
    for r in rows:
        w.writerow([r["id"], r["customer_name"], r["site_name"], r["template_slug"],
                    r["status"], r["inspector"], r["started_at"], r["completed_at"]])
    from flask import Response
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=inspections.csv"})


@app.route("/admin/export/deficiencies.csv")
@login_required
@admin_required
def export_deficiencies_csv():
    conn = get_conn()
    rows = conn.execute("""
        SELECT d.id, s.customer_name, s.site_name, d.item_label, d.description,
               d.severity, d.status, d.assigned_to, d.due_date,
               d.resolution_notes, d.created_at, d.resolved_at
        FROM deficiencies d JOIN sites s ON s.id = d.site_id
        ORDER BY d.created_at DESC
    """).fetchall()
    conn.close()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id","customer","site","item","description","severity","status",
                "assigned_to","due_date","resolution_notes","created_at","resolved_at"])
    for r in rows:
        w.writerow([r["id"], r["customer_name"], r["site_name"], r["item_label"],
                    r["description"], r["severity"], r["status"], r["assigned_to"],
                    r["due_date"], r["resolution_notes"], r["created_at"], r["resolved_at"]])
    from flask import Response
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=deficiencies.csv"})


# ---------- invoices ----------
@app.route("/admin/invoices")
@login_required
@admin_required
def admin_invoices():
    conn = get_conn()
    rows = conn.execute("""
        SELECT inv.*, s.customer_name, s.site_name
        FROM invoices inv JOIN sites s ON s.id = inv.site_id
        ORDER BY inv.created_at DESC
    """).fetchall()
    conn.close()
    return render_template("admin_invoices.html", invoices=rows)


@app.route("/admin/invoices/create", methods=["POST"])
@login_required
@admin_required
def create_invoice():
    f = request.form
    inspection_id = f.get("inspection_id") or None
    site_id = int(f.get("site_id"))
    amount_str = f.get("amount", "0").replace("$", "").replace(",", "").strip()
    try:
        amount_cents = int(float(amount_str) * 100)
    except Exception:
        amount_cents = 0
    description = f.get("description", "").strip()
    conn = get_conn()
    conn.execute("""
        INSERT INTO invoices (inspection_id, site_id, amount_cents, description, status, created_at)
        VALUES (?,?,?,?,'draft',?)
    """, (inspection_id, site_id, amount_cents, description,
          datetime.utcnow().isoformat(timespec="seconds")))
    conn.commit(); conn.close()
    log_event(session["user_id"], "invoice_created", "site", site_id, description[:60])
    flash("Invoice created as draft.", "success")
    return redirect(url_for("admin_invoices"))


@app.route("/admin/invoices/<int:inv_id>/status", methods=["POST"])
@login_required
@admin_required
def invoice_status(inv_id):
    new_status = request.form.get("status")
    if new_status not in ("draft", "sent", "paid"):
        abort(400)
    conn = get_conn()
    extra = ""
    vals = [new_status]
    if new_status == "paid":
        extra = ", paid_at=?"
        vals.append(datetime.utcnow().isoformat(timespec="seconds"))
    elif new_status == "sent":
        extra = ", sent_at=?"
        vals.append(datetime.utcnow().isoformat(timespec="seconds"))
    vals.append(inv_id)
    conn.execute(f"UPDATE invoices SET status=?{extra} WHERE id=?", vals)
    conn.commit(); conn.close()
    flash(f"Invoice marked {new_status}.", "success")
    return redirect(url_for("admin_invoices"))


# ---------- QuickBooks (stub / groundwork) ----------
@app.route("/admin/quickbooks")
@login_required
@admin_required
def admin_quickbooks():
    conn = get_conn()
    cfg = conn.execute("SELECT * FROM quickbooks_config WHERE id=1").fetchone()
    conn.close()
    return render_template("admin_quickbooks.html", cfg=cfg)


@app.route("/admin/quickbooks/connect")
@login_required
@admin_required
def qb_connect():
    flash("QuickBooks OAuth2 integration coming soon. Your invoice data is ready to sync once connected.", "success")
    return redirect(url_for("admin_quickbooks"))


@app.route("/admin/quickbooks/disconnect", methods=["POST"])
@login_required
@admin_required
def qb_disconnect():
    conn = get_conn()
    conn.execute("DELETE FROM quickbooks_config WHERE id=1")
    conn.commit(); conn.close()
    flash("QuickBooks disconnected.", "success")
    return redirect(url_for("admin_quickbooks"))


# ---------- bulk device import ----------
@app.route("/sites/<int:site_id>/devices/import", methods=["POST"])
@login_required
def import_devices(site_id):
    conn = get_conn()
    site = conn.execute("SELECT id FROM sites WHERE id=?", (site_id,)).fetchone()
    if not site:
        conn.close(); abort(404)
    f = request.files.get("csvfile")
    if not f:
        flash("No file uploaded.", "error")
        return redirect(url_for("site_detail", site_id=site_id))
    try:
        text = f.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        count = 0
        for row in reader:
            device_type = (row.get("device_type") or "extinguisher").strip()
            barcode = (row.get("barcode") or "").strip() or None
            model = (row.get("model") or "").strip() or None
            serial = (row.get("serial") or "").strip() or None
            location = (row.get("location") or "").strip() or None
            conn.execute("""
                INSERT INTO devices (site_id, device_type, barcode, model, serial, location)
                VALUES (?,?,?,?,?,?)
            """, (site_id, device_type, barcode, model, serial, location))
            count += 1
        conn.commit()
        log_event(session["user_id"], "devices_imported", "site", site_id, f"{count} devices")
        flash(f"{count} devices imported.", "success")
    except Exception as e:
        flash(f"Import failed: {e}", "error")
    conn.close()
    return redirect(url_for("site_detail", site_id=site_id))


# ---------- entry ----------
if __name__ == "__main__":
    print("")
    print("  IGH fireNspec - http://localhost:5000")
    print("  login: inspector / igh2026  (admin / igh2026 for admin features)")
    print("")
    app.run(host="0.0.0.0", port=5000, debug=True)
