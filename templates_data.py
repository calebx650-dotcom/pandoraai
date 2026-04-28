"""Inspection template definitions used by IGH fireNspec.

Each template is a list of sections; each section is a list of checklist items.
Items support: id (slug), label, type ('check' = Pass/Fail/NA, 'text', 'number').

Templates can be edited at runtime by an admin via /admin/templates -- the edits
are merged from custom_templates.json on import.
"""
import json
import os

TEMPLATES = {
    "fire_extinguisher": {
        "name": "Fire Extinguisher - Annual",
        "icon": "FE",
        "frequency_months": 12,
        "sections": [
            {
                "title": "Mounting & Access",
                "items": [
                    {"id": "fe_accessible", "label": "Extinguisher accessible & unobstructed", "type": "check"},
                    {"id": "fe_signage", "label": "Signage visible from approach", "type": "check"},
                    {"id": "fe_height", "label": "Mounted at correct height (<= 5 ft)", "type": "check"},
                    {"id": "fe_bracket", "label": "Bracket / cabinet secure", "type": "check"},
                ],
            },
            {
                "title": "Cylinder & Components",
                "items": [
                    {"id": "fe_pressure", "label": "Pressure gauge in green zone", "type": "check"},
                    {"id": "fe_pin", "label": "Safety pin & tamper seal intact", "type": "check"},
                    {"id": "fe_hose", "label": "Hose / horn free of cracks", "type": "check"},
                    {"id": "fe_corrosion", "label": "No dents, rust, or corrosion", "type": "check"},
                    {"id": "fe_label", "label": "Label & instructions legible", "type": "check"},
                ],
            },
            {
                "title": "Servicing",
                "items": [
                    {"id": "fe_weight", "label": "Weighed - within tolerance", "type": "check"},
                    {"id": "fe_tag", "label": "Inspection tag updated", "type": "check"},
                    {"id": "fe_hydro_due", "label": "Next hydrostatic test (year)", "type": "number"},
                ],
            },
        ],
    },
    "fire_alarm": {
        "name": "Fire Alarm System",
        "icon": "FA",
        "frequency_months": 12,
        "sections": [
            {
                "title": "Control Panel",
                "items": [
                    {"id": "fa_panel_power", "label": "AC power LED on, no trouble lights", "type": "check"},
                    {"id": "fa_battery", "label": "Backup battery voltage OK", "type": "check"},
                    {"id": "fa_event_log", "label": "Event log reviewed & cleared", "type": "check"},
                ],
            },
            {
                "title": "Initiating Devices",
                "items": [
                    {"id": "fa_smoke", "label": "Smoke detectors tested", "type": "check"},
                    {"id": "fa_heat", "label": "Heat detectors tested", "type": "check"},
                    {"id": "fa_pulls", "label": "Manual pull stations tested", "type": "check"},
                    {"id": "fa_duct", "label": "Duct detectors tested", "type": "check"},
                ],
            },
            {
                "title": "Notification Appliances",
                "items": [
                    {"id": "fa_horns", "label": "Horns audible (>= 75 dB)", "type": "check"},
                    {"id": "fa_strobes", "label": "Strobes synchronized", "type": "check"},
                    {"id": "fa_voice", "label": "Voice evacuation intelligible", "type": "check"},
                ],
            },
            {
                "title": "Communication",
                "items": [
                    {"id": "fa_monitor", "label": "Central station signal received", "type": "check"},
                    {"id": "fa_dialer", "label": "Dialer / IP communicator OK", "type": "check"},
                ],
            },
        ],
    },
    "kitchen_suppression": {
        "name": "Kitchen Hood Suppression",
        "icon": "KS",
        "frequency_months": 6,
        "sections": [
            {
                "title": "Hood & Ducts",
                "items": [
                    {"id": "ks_hood_clean", "label": "Hood and filters cleaned", "type": "check"},
                    {"id": "ks_grease", "label": "No grease accumulation in plenum", "type": "check"},
                ],
            },
            {
                "title": "Suppression System",
                "items": [
                    {"id": "ks_nozzles", "label": "Nozzles aimed at appliances, caps in place", "type": "check"},
                    {"id": "ks_tank", "label": "Agent tank pressure OK", "type": "check"},
                    {"id": "ks_fusible", "label": "Fusible links replaced (semi-annual)", "type": "check"},
                    {"id": "ks_pull", "label": "Manual pull station accessible", "type": "check"},
                    {"id": "ks_gas", "label": "Gas/electric shutoff verified", "type": "check"},
                ],
            },
            {
                "title": "Documentation",
                "items": [
                    {"id": "ks_tag", "label": "Tag updated with date & inspector", "type": "check"},
                    {"id": "ks_ahj", "label": "AHJ contact recorded", "type": "text"},
                ],
            },
        ],
    },
    "emergency_lighting": {
        "name": "Emergency & Exit Lighting",
        "icon": "EL",
        "frequency_months": 12,
        "sections": [
            {
                "title": "Exit Signs",
                "items": [
                    {"id": "el_exit_lit", "label": "All exit signs illuminated", "type": "check"},
                    {"id": "el_exit_path", "label": "Egress path clear & marked", "type": "check"},
                ],
            },
            {
                "title": "Emergency Lights",
                "items": [
                    {"id": "el_30s", "label": "30-second monthly test passed", "type": "check"},
                    {"id": "el_90min", "label": "90-minute annual discharge passed", "type": "check"},
                    {"id": "el_battery", "label": "Battery & lamps OK", "type": "check"},
                ],
            },
        ],
    },
    "firewatch": {
        "name": "Firewatch Patrol (IGH)",
        "icon": "FW",
        "frequency_months": 0,
        "is_firewatch": True,
        "sections": [
            {
                "title": "Pre-Patrol Sign-On",
                "items": [
                    {"id": "fw_authority", "label": "Approved by AHJ / property contact (name)", "type": "text"},
                    {"id": "fw_reason", "label": "Reason for firewatch", "type": "text"},
                    {"id": "fw_systems_offline", "label": "Systems offline (alarm/sprinkler/etc.)", "type": "text"},
                    {"id": "fw_route", "label": "Patrol route briefed & understood", "type": "check"},
                    {"id": "fw_extinguisher", "label": "Portable extinguisher carried", "type": "check"},
                    {"id": "fw_phone", "label": "911 / dispatch number on hand", "type": "check"},
                ],
            },
            {
                "title": "End-of-Shift Sign-Off",
                "items": [
                    {"id": "fw_handoff", "label": "Handed off to (name, time)", "type": "text"},
                    {"id": "fw_summary", "label": "Shift summary / incidents", "type": "text"},
                ],
            },
        ],
    },
}


# --- runtime template overrides (admin-edited) -----------------------------
_OVERRIDES = os.path.join(os.path.dirname(__file__), "custom_templates.json")
try:
    if os.path.exists(_OVERRIDES):
        with open(_OVERRIDES, "r", encoding="utf-8") as f:
            for slug, body in json.load(f).items():
                TEMPLATES[slug] = body
except Exception as e:
    print("templates_data: could not load overrides:", e)


def save_overrides():
    """Persist current TEMPLATES to custom_templates.json so admin edits survive restarts."""
    with open(_OVERRIDES, "w", encoding="utf-8") as f:
        json.dump(TEMPLATES, f, indent=2)


def get_template(slug):
    return TEMPLATES.get(slug)


def all_items(template_slug):
    """Flatten template into a list of item dicts with section info."""
    tmpl = TEMPLATES[template_slug]
    out = []
    for section in tmpl["sections"]:
        for item in section["items"]:
            out.append({**item, "section": section["title"]})
    return out
