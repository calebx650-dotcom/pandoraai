# Spectofire - Mobile Inspection MVP

A mobile-friendly fire-safety inspection app built for **IGH Health, Fire & Safety** (DFW). Modeled on the workflow of Spectofire Pro, rebuilt as a Python/Flask MVP.

The web UI is mobile-first and PWA-ready, so technicians can "Add to Home Screen" on iPhone/iPad and use it like a native app.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000` (or `http://<your-LAN-ip>:5000` from a phone on the same WiFi).

## Logins

| Username  | Password | Role      | What they can do                                  |
|-----------|----------|-----------|---------------------------------------------------|
| inspector | igh2026  | Inspector | All inspection work, sites, devices, reports      |
| admin     | igh2026  | Admin     | Inspector access + template editor + activity log |

## Spectofire parity feature checklist

| Capability                                | Status |
|-------------------------------------------|--------|
| Multiple inspection templates             | yes    |
| Customizable templates (admin editor, JSON) | yes  |
| CRM-style customer / site records         | yes    |
| Device tracking (barcode, model, serial)  | yes    |
| Barcode scanner (HTML5 BarcodeDetector + manual fallback) | yes |
| Pre-fill from device history              | yes    |
| Pass / Fail / N/A checklist               | yes    |
| Per-item notes with auto-save             | yes    |
| Photo capture / upload (camera-enabled)   | yes    |
| Drawn signature capture (canvas, touch)   | yes    |
| GPS tag at start + on each round          | yes    |
| Real-time chat / comments per inspection  | yes    |
| Real-time event / activity log (admin)    | yes    |
| Print / save-as-PDF report                | yes    |
| Email report to customer (mailto)         | yes    |
| Auto-bump device next-due dates on completion | yes |
| **Firewatch patrol logger** (IGH service line) | yes |
| Offline shell cache (PWA service worker)  | yes    |
| Online/offline indicator                  | yes    |

## Templates included out of the box

- Fire extinguisher (annual)
- Fire alarm system
- Kitchen hood suppression (semi-annual)
- Emergency & exit lighting
- **Firewatch patrol** - timed-round logger for hot-work / impaired-system shifts

Admins can add more templates via `/admin/templates` (JSON form). Saved overrides persist in `custom_templates.json`.

## Project layout

```
firenspec_igh/
|- app.py                  # Flask app + all routes
|- db.py                   # SQLite schema + seed + log_event()
|- templates_data.py       # Inspection templates (overlayed by custom_templates.json)
|- requirements.txt
|- static/
|  |- style.css            # Brand: navy #13334A + orange #E84E2C
|  |- app.js               # auto-save, sig pad, barcode scanner, GPS
|  |- manifest.webmanifest # PWA manifest
|  |- sw.js                # Service worker
|  |- logo.svg             # IGH-style shield
|  |- uploads/<id>/...     # Photo uploads (created at runtime)
|- templates/
   |- base.html            # Layout + tabbar (admin tab when role=admin)
   |- login.html
   |- dashboard.html
   |- sites.html, new_site.html, site_detail.html
   |- new_inspection.html
   |- inspection.html      # Big one: checklist, rounds, photos, comments, sig
   |- report.html          # Print/PDF + mailto
   |- reports.html
   |- admin_templates.html
   |- admin_events.html
```

## REST endpoints

```
GET  /                                   dashboard
GET/POST /login                          auth
GET  /logout

GET  /sites?q=...                        list / search sites
GET/POST /sites/new
GET  /sites/<id>
POST /sites/<id>/devices/new

GET/POST /inspect/new                    start inspection (with optional GPS, device_id)
GET  /inspections/<id>                   inspection editor
POST /inspections/<id>/save              auto-save (item_id, result, note)
POST /inspections/<id>/round             firewatch: log a patrol round
POST /inspections/<id>/comment           add chat comment
POST /inspections/<id>/photo             upload photo (multipart)
POST /inspections/<id>/signature         save canvas signature (data URL, who=inspector|customer)
POST /inspections/<id>/complete          finalize + redirect to report
GET  /inspections/<id>/report
GET  /reports

GET  /api/lookup_barcode?code=...        device lookup by barcode/serial

# admin only
GET/POST /admin/templates                template editor
POST /admin/templates/<slug>/delete
GET  /admin/events                       last 200 audit events

GET  /manifest.webmanifest
GET  /sw.js
GET  /static/uploads/<id>/<filename>
```

## Bugs / UX improvements vs. typical Spectofire complaints

1. **Lost edits on navigation** - every change auto-POSTs, "Saved" indicator in header.
2. **Tiny tap targets** - 48px minimum on every control (iOS HIG).
3. **Re-typing device info** - devices persist per site; barcode lookup pre-fills.
4. **Hard-to-find report** - one-tap "View Report" / "Print" / "Email" on every completed inspection.
5. **No offline indicator** - live online/offline pill in topbar; service worker caches the shell.
6. **Confusing nested menus** - flat 4-tab bottom nav (Home / Inspect / Sites / Reports), plus Admin tab if you have the role.
7. **Typed signatures only** - real drawn signature pad on canvas (touch-friendly).
8. **No firewatch flow** - dedicated patrol-round logger with auto-GPS.
