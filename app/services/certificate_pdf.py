"""
Nikah Nama PDF: the layout lives in templates/nikah/_paper_css.html + _paper_js.html
(shared with the live preview). This renders it in headless Chromium and exports A4.

Setup:  pip install playwright   &&   playwright install chromium
"""
from datetime import date, datetime, time as dtime
from decimal import Decimal

from flask import render_template

_FIELDS = (
    "sanad_no", "jild_no", "nikah_date", "nikah_time",
    "nikah_location", "nikah_location_ur",
    "groom_name", "groom_name_ur", "groom_age", "groom_address", "groom_address_ur",
    "bride_name", "bride_name_ur", "bride_age", "bride_address", "bride_address_ur",
    "vakil_name", "vakil_name_ur", "vakil_age", "vakil_address", "vakil_address_ur",
    "witness1_name", "witness1_name_ur", "witness1_age", "witness1_address", "witness1_address_ur",
    "witness2_name", "witness2_name_ur", "witness2_age", "witness2_address", "witness2_address_ur",
    "maher_amount", "dower_type",
    "qazi_name", "qazi_name_ur", "qazi_address", "qazi_address_ur", "qazi_signature",
)


def _normalize(v):
    """DB values -> JSON-safe strings, matching what the browser form sends."""
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, dtime):
        return f"{v.hour:02d}:{v.minute:02d}"
    if isinstance(v, (Decimal, float)):
        return str(int(v)) if v == int(v) else str(v)
    return v


def _record_to_dict(record):
    get = record.get if isinstance(record, dict) else (lambda k, d=None: getattr(record, k, d))
    return {f: _normalize(get(f, "")) for f in _FIELDS}


def render_nikah_certificate_pdf(record) -> bytes:
    from playwright.sync_api import sync_playwright   # lazy: app still boots without it

    html = render_template("print/nikah_certificate.html", data=_record_to_dict(record))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.wait_for_selector('body[data-ready="1"]', timeout=20000)
            return page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "8mm", "bottom": "8mm", "left": "8mm", "right": "8mm"},
            )
        finally:
            browser.close()