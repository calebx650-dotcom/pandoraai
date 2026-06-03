# IGH FireNspec / Spectofire — Full App Analysis

> Generated from full codebase review of `app.py`, `db.py`, `templates_data.py`, all templates, and `static/style.css`.

---

## 1. Core Capabilities

### What the app does
IGH FireNspec is a **mobile-first fire safety inspection management platform** for IGH Health, Fire & Safety, LLC. Field inspectors run checklists on-site, log deficiencies, upload photos, collect digital signatures, and generate PDF-ready reports — all from their phone. Admins manage scheduling, invoicing, and users from the same app.

### Inspection types (templates)
| Template slug | Name | Frequency |
|---|---|---|
| `fire_extinguisher` | Fire Extinguisher Annual | 12 months |
| `fire_alarm` | Fire Alarm System | 12 months |
| `kitchen_suppression` | Kitchen Hood Suppression | 6 months |
| `emergency_lighting` | Emergency Lighting | 12 months |
| `firewatch` | Firewatch Log | per-shift |

### Main user workflows
1. **Start inspection** → select site + template → GPS captured → checklist opens
2. **Work checklist** → Pass/Fail/NA per item → auto-saves every change → add notes
3. **Log deficiency** → triggered from any Fail item → severity/assignee/due date
4. **Add photos + signatures** → camera upload + canvas signature pad
5. **Complete inspection** → customer email + notes → schedule auto-advances → report page
6. **Email report** → one tap sends via Resend to customer contact email
7. **Firewatch shift** → log 15-min rounds with GPS + observations + all-clear flag
8. **View dashboard** → overdue devices, hydro tests due, upcoming schedules, in-progress jobs
9. **Resolve deficiency** → resolution notes → status → audit logged
10. **Create invoice** → link to site/inspection → draft/sent/paid lifecycle

### Forms and data fields
- **Site**: customer_name, site_name, address, contact_name, contact_phone, contact_email, notes, portal_token
- **Device**: device_type, barcode, serial, model, location, extinguisher_type, extinguisher_size, manufactured_date, last_service_date, last_inspected, next_due, qr_token, notes
- **Inspection**: site, template, inspector, GPS lat/lng, notes, customer_email, inspector_signature, customer_signature
- **Checklist item**: pass / fail / NA + free-text note per item
- **Deficiency**: description, severity (critical/major/minor), assigned_to, due_date, resolution_notes
- **Firewatch round**: location, observations, all_clear, GPS lat/lng
- **Invoice**: site, inspection, amount, description, status (draft/sent/paid)
- **Schedule**: site, template_slug, frequency_months, next_due, notes

### Dashboard alerts
- Open deficiencies count (warning color if > 0)
- Unpaid invoices count (admin only)
- Hydrostatic test overdue / due-soon (extinguishers ≥ 7 yrs since manufacture)
- Overdue device inspections (next_due in the past)
- Upcoming device inspections (next 30 days)
- Scheduled site inspections due this month
- In-progress inspections (yours, by inspector)
- Last 10 completed reports

### Automation and tracking
- **Auto-save**: every Pass/Fail/NA click and note change POSTs to `/inspections/:id/save`
- **Schedule auto-advance**: completing an inspection pushes `site_schedules.next_due` forward by `frequency_months`
- **Device next_due**: completing an inspection also updates matching `devices.next_due`
- **7-year hydrostatic tracking**: `expiration_status()` calculates years since `manufactured_date`
- **QR token backfill**: `init_db()` generates tokens for any extinguisher missing one
- **Audit log**: every meaningful action logged to `events` table with user/target/timestamp
- **Deficiency email**: logging a deficiency auto-sends email to site contact via Resend
- **Portal token**: admin generates tokenized URL → customer views reports + deficiencies without login
- **PWA**: service worker + manifest registered for offline-capable install on mobile

### Navigation structure
```
Bottom tabbar (all users):
  🏠 Home (dashboard)
  📍 Sites (site list + search)
  🔍 Inspect (new inspection)
  📄 Reports (completed list)

Topbar right (admin only):
  Admin menu → Users / Templates / Schedules / Invoices / QuickBooks / Events / CSV Exports

Public:
  /portal/:token  → customer-facing report + deficiency view
  /qr/:token      → QR scan → login → device detail
```

---

## 2. UI/UX Notes

### Layout structure
- Single-column, max-width **720px**, centered, padded 16px sides
- **Sticky topbar** (navy `#13334A`) with logo, page title, and online/offline indicator
- **Fixed bottom tabbar** with 4 tabs + safe-area inset for iPhone home bar
- **Content area** scrolls between topbar and tabbar, `padding-bottom: 88px`
- **FAB** (`+` floating button, orange) on dashboard and sites pages for quick new inspection

### Color system
| Token | Hex | Used for |
|---|---|---|
| `--igh-orange` | `#E84E2C` | CTAs, active tab, links, FAB |
| `--igh-navy` | `#13334A` | Topbar, headings |
| `--bg` | `#F5F6F8` | Page background |
| `--card` | `#FFFFFF` | Card surfaces |
| `--pass` | `#1F8B4C` | Pass result |
| `--fail` | `#C5283D` | Fail result + critical deficiency |
| `--warn` | `#D77A00` | Due-soon / warning |
| `--na` | `#6E6E79` | N/A result |

### Card and list patterns
- **Card**: white, 14px radius, box-shadow, 16px margin, `overflow: hidden`
- **Card row**: `padding: 14px 16px`, min-height 48px (tap target), `border-top` divider
- **Row structure**: `[icon] [meta: title + subtitle] [pill badge] [chevron ›]`
- **Pill badge**: `overdue` (red), `due-soon` (amber), `in_progress` (navy), `completed` (green)
- **Segmented control**: Pass / Fail / NA buttons, active state colored by result type

### Visual patterns
- **Stats row**: 4 horizontal cards with large number + label, warn color when non-zero
- **Relative timestamps**: "2h ago", "3d ago" throughout
- **Empty state**: centered italic text in card — "No completed reports yet."
- **Flash messages**: success/error banners at top of content
- **Section headers** (`card-title`): small caps, ink-2 color, 16px margin-left

### What works well
- 48px minimum tap targets throughout (mobile-safe)
- Auto-save removes friction — no explicit "save" button on checklists
- Fail → deficiency button visibility via JS feels natural
- Portal link gives customers self-service access without login friction
- QR scan → device detail is a clean field workflow
- Dashboard surfaces the most urgent items (hydro overdue, deficiencies, overdue devices) immediately

### Friction points / UX gaps
- No offline queue — if connection drops mid-inspection, changes are lost
- Signature capture is canvas only — no DocuSign/typed name fallback
- No push notifications — inspectors don't get alerted to overdue items
- Admin-only scheduling means inspectors can't see their own upcoming jobs
- No search on reports page
- No bulk resolve for deficiencies
- No inline photo annotation
- Invoice PDF generation not implemented — currently print-from-browser only
- QuickBooks OAuth2 is stubbed but not connected

---

## 3. Frontend Plan (React / Next.js)

### Pages / screens needed

| Route | Page | Role |
|---|---|---|
| `/login` | Login | public |
| `/` | Dashboard | all |
| `/sites` | Site list + search | all |
| `/sites/new` | New site form | all |
| `/sites/[id]` | Site detail + devices + history | all |
| `/sites/[id]/edit` | Edit site | all |
| `/devices/[id]` | Device detail + QR + history | all |
| `/inspect/new` | Start inspection (select site + template) | all |
| `/inspections/[id]` | Active checklist | all |
| `/inspections/[id]/report` | Completed report | all |
| `/reports` | All completed reports | all |
| `/deficiencies` | Deficiency list (open/all filter) | all |
| `/portal/[token]` | Customer portal | public |
| `/qr/[token]` | QR redirect | public |
| `/admin/users` | User management | admin |
| `/admin/users/new` | New user form | admin |
| `/admin/users/[id]/edit` | Edit user | admin |
| `/admin/schedules` | Schedule management | admin |
| `/admin/invoices` | Invoice list + create | admin |
| `/admin/templates` | Template JSON editor | admin |
| `/admin/quickbooks` | QuickBooks config | admin |
| `/admin/events` | Audit log | admin |

### Components needed

```
components/
├── layout/
│   ├── TopBar.tsx          # sticky navy bar with logo + title + conn status
│   ├── TabBar.tsx          # fixed bottom 4-tab nav
│   ├── FAB.tsx             # floating action button
│   └── PageHead.tsx        # h2 + subtitle section
│
├── ui/
│   ├── Card.tsx            # white card with shadow + overflow hidden
│   ├── CardRow.tsx         # [icon] [meta] [pill] [chevron] row
│   ├── PillBadge.tsx       # overdue / due-soon / in-progress / completed
│   ├── StatCard.tsx        # large number stat with label
│   ├── FlashBanner.tsx     # success/error messages
│   ├── EmptyState.tsx      # centered italic placeholder
│   └── SectionHeader.tsx   # card-title label
│
├── forms/
│   ├── SiteForm.tsx        # new/edit site fields
│   ├── DeviceForm.tsx      # new/edit device fields
│   ├── DeficiencyForm.tsx  # severity + description + due date
│   ├── InvoiceForm.tsx     # amount + description + site selector
│   └── ScheduleForm.tsx    # site + template + frequency + next_due
│
├── inspection/
│   ├── SegmentedControl.tsx    # Pass / Fail / NA per item
│   ├── ChecklistSection.tsx    # section title + list of items
│   ├── ChecklistItem.tsx       # single item: label + segment + note + deficiency btn
│   ├── SignatureCanvas.tsx     # canvas pad for inspector + customer sigs
│   ├── PhotoUploader.tsx       # drag-drop + camera capture + caption
│   ├── FirewatchRoundForm.tsx  # location + observations + all-clear + GPS
│   └── CommentThread.tsx       # comment list + add comment
│
├── dashboard/
│   ├── StatsRow.tsx            # 4 stat cards
│   ├── AlertList.tsx           # hydro due / overdue / upcoming
│   └── ScheduledList.tsx       # this month's scheduled inspections
│
└── devices/
    ├── QRCodeViewer.tsx        # display + download QR PNG
    └── ExpirationBadge.tsx     # ok / due-soon / overdue status
```

### Suggested Next.js structure

```
app/
├── (auth)/
│   └── login/page.tsx
├── (app)/
│   ├── layout.tsx              # TopBar + TabBar shell
│   ├── page.tsx                # Dashboard
│   ├── sites/
│   │   ├── page.tsx
│   │   ├── new/page.tsx
│   │   └── [id]/
│   │       ├── page.tsx
│   │       └── edit/page.tsx
│   ├── devices/[id]/page.tsx
│   ├── inspect/
│   │   ├── new/page.tsx
│   │   └── [id]/
│   │       ├── page.tsx        # active checklist
│   │       └── report/page.tsx
│   ├── reports/page.tsx
│   ├── deficiencies/page.tsx
│   └── admin/
│       ├── users/
│       ├── schedules/
│       ├── invoices/
│       ├── templates/
│       ├── quickbooks/
│       └── events/
├── portal/[token]/page.tsx
├── qr/[token]/page.tsx
└── api/
    └── [...all API routes]

lib/
├── db.ts                       # Prisma or raw sqlite3 client
├── auth.ts                     # session helpers
└── mailer.ts                   # email via Resend

hooks/
├── useAutoSave.ts              # debounced auto-save per checklist item
├── useGPS.ts                   # navigator.geolocation wrapper
├── useOnline.ts                # online/offline detection
└── useInspection.ts            # inspection state manager
```

### Mobile vs desktop layout
- **Mobile** (< 720px): single column, bottom tabbar always visible, 48px tap targets, full-width cards
- **Desktop** (≥ 720px): max-width 720px centered OR add a left sidebar for admin nav
- **Checklist page**: stacks vertically, segment control stays full-width, auto-scroll to active item
- **Report page**: printable CSS media query, `@media print` hides nav, shows full report

---

## 4. Backend / Data Plan

### Current database (SQLite via raw sqlite3)

| Table | Key fields | Notes |
|---|---|---|
| `users` | id, username, password_hash, full_name, role, active | roles: `inspector`, `admin` |
| `sites` | id, customer_name, site_name, address, contact_*, notes, portal_token | portal_token unique per site |
| `devices` | id, site_id, device_type, barcode, serial, model, location, last_inspected, next_due, manufactured_date, qr_token | device_types: extinguisher, fire_alarm_panel, kitchen_suppression, emergency_light |
| `inspections` | id, site_id, inspector_id, template_slug, status, started_at, completed_at, gps_lat/lng, signatures, device_id | status: in_progress, completed |
| `inspection_items` | id, inspection_id, item_id, result, note | result: pass, fail, na |
| `firewatch_rounds` | id, inspection_id, round_no, started_at, location, observations, all_clear, gps_lat/lng | |
| `inspection_photos` | id, inspection_id, device_id, item_id, filename, caption, uploaded_at | stored on disk |
| `inspection_comments` | id, inspection_id, user_id, body, created_at | |
| `events` | id, user_id, action, target_type, target_id, detail, created_at | full audit trail |
| `deficiencies` | id, inspection_id, site_id, item_id, item_label, description, severity, status, assigned_to, due_date, resolution_notes, created_by, resolved_at | severity: critical, major, minor |
| `site_schedules` | id, site_id, template_slug, frequency_months, next_due, notes | auto-advances on completion |
| `invoices` | id, inspection_id, site_id, status, amount_cents, description, qb_invoice_id, sent_at, paid_at | status: draft, sent, paid |
| `quickbooks_config` | id=1, qb_realm_id, access_token, refresh_token, token_expires_at | singleton row |

### Tables to add (gaps identified)

```sql
-- Push notification subscriptions
CREATE TABLE push_subscriptions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    endpoint TEXT NOT NULL,
    p256dh TEXT,
    auth TEXT,
    created_at TEXT NOT NULL
);

-- Invoice line items (currently single-amount only)
CREATE TABLE invoice_line_items (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    quantity REAL DEFAULT 1,
    unit_price_cents INTEGER NOT NULL
);

-- Device maintenance / service records
CREATE TABLE device_service_records (
    id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    service_type TEXT,        -- annual, 6yr, hydrostatic, repair
    serviced_by TEXT,
    serviced_at TEXT,
    notes TEXT,
    cost_cents INTEGER
);
```

### User roles
| Role | Access |
|---|---|
| `inspector` | dashboard, all sites, start/run/complete inspections, add deficiencies, upload photos |
| `admin` | everything above + user mgmt, schedule mgmt, invoices, template editor, QB, CSV exports, delete |
| (future) `viewer` | read-only dashboard + reports, no inspection actions |
| (future) `customer` | portal only (tokenized, no login) |

### API endpoints (target REST design)

```
Auth
  POST   /api/auth/login
  DELETE /api/auth/logout
  GET    /api/auth/me

Sites
  GET    /api/sites                    # list + ?q=search
  POST   /api/sites
  GET    /api/sites/:id
  PATCH  /api/sites/:id
  GET    /api/sites/:id/devices
  POST   /api/sites/:id/devices
  GET    /api/sites/:id/inspections
  GET    /api/sites/:id/schedules
  POST   /api/sites/:id/portal-token
  POST   /api/sites/:id/devices/import  # CSV bulk import

Devices
  GET    /api/devices/:id
  PATCH  /api/devices/:id
  GET    /api/devices/:id/qr.png
  POST   /api/devices/:id/regen-qr
  GET    /api/devices/lookup?code=:barcode
  GET    /api/qr/:token                 # resolve token → device id

Inspections
  GET    /api/inspections               # ?status=in_progress|completed
  POST   /api/inspections               # start
  GET    /api/inspections/:id
  POST   /api/inspections/:id/save      # auto-save item
  POST   /api/inspections/:id/complete
  POST   /api/inspections/:id/signature
  POST   /api/inspections/:id/photo
  POST   /api/inspections/:id/comment
  POST   /api/inspections/:id/round     # firewatch
  POST   /api/inspections/:id/email     # send report
  GET    /api/inspections/:id/report    # full report data

Deficiencies
  GET    /api/deficiencies              # ?status=open|all
  POST   /api/inspections/:id/deficiencies
  PATCH  /api/deficiencies/:id          # resolve
  DELETE /api/deficiencies/:id          # admin

Schedules (admin)
  GET    /api/schedules
  POST   /api/schedules
  DELETE /api/schedules/:id

Invoices (admin)
  GET    /api/invoices
  POST   /api/invoices
  PATCH  /api/invoices/:id/status

Users (admin)
  GET    /api/admin/users
  POST   /api/admin/users
  PATCH  /api/admin/users/:id

Templates (admin)
  GET    /api/admin/templates
  PUT    /api/admin/templates/:slug
  DELETE /api/admin/templates/:slug

Events (admin)
  GET    /api/admin/events

CSV exports (admin)
  GET    /api/admin/export/sites.csv
  GET    /api/admin/export/inspections.csv
  GET    /api/admin/export/deficiencies.csv

Customer portal
  GET    /api/portal/:token             # site + inspections + deficiencies (no auth)
```

### File / image / report storage
- **Photos**: currently stored on disk in `uploads/:inspection_id/:filename`
- **Production**: Fly.io persistent volume (`DATA_DIR` env var)
- **Upgrade path**: move to S3/R2 with presigned URLs; store only URL in DB
- **Reports**: currently rendered HTML (print-to-PDF in browser)
- **Upgrade path**: server-side PDF via WeasyPrint or Puppeteer, stored on R2

---

## 5. Build Roadmap

### ✅ MVP (done — current Flask app)
- Login / session auth (inspector + admin roles)
- Site + device management
- Inspection checklist (fire extinguisher, alarm, firewatch, kitchen, emergency lighting)
- Auto-save per checklist item
- Photo upload + digital signatures
- Completed report page with pass/fail/na counts
- Email report via Resend
- Dashboard with overdue + upcoming + in-progress
- 7-year hydrostatic tracking for extinguishers
- QR code generation + scan landing
- PWA manifest + service worker registration

### 🔨 Version 2 (in progress — recent commits)
- [x] Deficiency tracking (create, assign, resolve)
- [x] Deficiency email notifications to site contact
- [x] User management (admin CRUD)
- [x] Inspection scheduling with auto-advance `next_due`
- [x] Invoice management (draft/sent/paid lifecycle)
- [x] QuickBooks groundwork (schema + stub routes)
- [x] Customer portal (tokenized, no login)
- [x] CSV exports (sites, inspections, deficiencies)
- [x] Audit event log (`/admin/events`)
- [x] Admin template editor (runtime JSON editing)
- [x] `/api/sites` JSON endpoint for dropdowns
- [x] Deficiency button show/hide via JS on fail result
- [x] All device types link to device_detail

### 🚀 Version 3 — React/Next.js Frontend Rebuild
Priority order:
1. **Next.js API layer** — migrate Flask routes to Next.js API routes, keep SQLite initially
2. **Core pages** — Dashboard, Sites, Inspection checklist, Report view
3. **Offline support** — IndexedDB queue for checklist saves, sync on reconnect
4. **Push notifications** — Web Push API for overdue alerts to inspector devices
5. **PDF generation** — server-side WeasyPrint or Puppeteer for report PDFs
6. **QuickBooks OAuth2** — real Intuit OAuth2 flow + invoice sync
7. **Barcode scanner** — `BarcodeDetector` API / ZXing for camera scanning on new inspection
8. **Admin dashboard** — charts: inspections by month, compliance rate, deficiency trends
9. **Photo annotations** — canvas overlay for marking up inspection photos
10. **Stripe invoice portal** — customer pays invoices directly from portal

### ⚡ Advanced Features (V4+)
- **Multi-tenant** — support multiple inspection companies under one platform
- **AI deficiency suggestions** — Claude API: describe item → auto-suggest standard deficiency description
- **Automated scheduling emails** — send "inspection due in 7 days" to site contacts automatically
- **React Native app** — true offline-first mobile app with background GPS tracking
- **AHJ (Authority Having Jurisdiction) reports** — NFPA-formatted export for city inspectors
- **Technician routing** — map view of all sites due this week, optimize driving route
- **Customer dashboard** — full customer login (not just token portal), multi-site view
- **Equipment lifecycle tracking** — full service history + warranty tracking per device
- **Recurring deficiency patterns** — flag sites that repeatedly fail the same item

### What to build first (priority order for next sprint)
1. **Offline checklist queue** — highest field impact, inspectors work in poor signal areas
2. **PDF report generation** — biggest customer-facing quality improvement
3. **Push notifications** — reduces missed overdue inspections
4. **Next.js migration** — modernize stack before adding more features
5. **QuickBooks real OAuth2** — revenue-enabling, schema already in place
