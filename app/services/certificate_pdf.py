"""
Nikah Nama PDF: renders the certificate as a server-side Jinja/CSS template
and converts it to an A4 PDF using Playwright (Chromium) / WeasyPrint / xhtml2pdf.

Setup:  pip install playwright   &&   playwright install chromium
"""
from datetime import date, datetime, time as dtime
from decimal import Decimal
import io
import os

from flask import render_template, current_app

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
    """DB values -> template-safe strings."""
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


def _format_date(iso_str):
    """Format ISO date string to DD/MM/YYYY and day name."""
    if not iso_str:
        return "", ""
    try:
        dt = datetime.strptime(str(iso_str), "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y"), dt.strftime("%A")
    except ValueError:
        return str(iso_str), ""


def _format_time(time_str):
    """Format HH:MM to 12-hour AM/PM."""
    if not time_str:
        return ""
    try:
        parts = str(time_str).split(":")
        h, m = int(parts[0]), int(parts[1])
        h12 = 12 if h % 12 == 0 else h % 12
        return f"{h12}:{m:02d} {'AM' if h < 12 else 'PM'}"
    except (ValueError, IndexError):
        return str(time_str)


def _format_amount(raw):
    """Format currency amount with comma grouping."""
    if not raw:
        return ""
    try:
        n = float(str(raw).replace(",", ""))
        formatted = f"{n:,.0f}" if n == int(n) else f"{n:,.2f}"
        return f"Rs. {formatted}"
    except (ValueError, TypeError):
        return str(raw)


def _record_to_dict(record):
    get = record.get if isinstance(record, dict) else (lambda k, d=None: getattr(record, k, d))
    d = {f: _normalize(get(f, "")) for f in _FIELDS}

    # Pre-formatted display values for the certificate template
    d["date_formatted"], d["day_name"] = _format_date(d.get("nikah_date"))
    d["time_formatted"] = _format_time(d.get("nikah_time"))
    d["maher_formatted"] = _format_amount(d.get("maher_amount"))

    # Date subtitle line: "Monday · 2:30 PM"
    sub_parts = [p for p in [d["day_name"], d["time_formatted"]] if p]
    d["date_sub"] = " · ".join(sub_parts)

    # Serial display: "Vol. 1  /  No. 42"
    serial_parts = []
    if d.get("jild_no"):
        serial_parts.append(f"Vol. {d['jild_no']}")
    if d.get("sanad_no"):
        serial_parts.append(f"No. {d['sanad_no']}")
    d["serial_display"] = "  /  ".join(serial_parts)

    # Combined qazi name for the signature line
    qazi_parts = [p for p in [d.get("qazi_name", ""), d.get("qazi_name_ur", "")] if p]
    d["qazi_display"] = "  ".join(qazi_parts)

    return d


def render_nikah_certificate_pdf(record) -> bytes:
    """Render a Nikah Nama record as a single-page A4 PDF using Playwright (or fallback)."""
    data = _record_to_dict(record)
    html = render_template("print/nikah_certificate.html", data=data)

    # 1. Primary: Playwright headless Chromium for perfect 1:1 CSS/Font rendering
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                return page.pdf(
                    format="A4",
                    print_background=True,
                    margin={"top": "8mm", "bottom": "8mm", "left": "8mm", "right": "8mm"},
                )
            finally:
                browser.close()
    except Exception as exc:
        current_app.logger.warning("Playwright rendering unavailable: %s. Falling back to WeasyPrint/xhtml2pdf.", exc)

    # 2. Secondary: WeasyPrint
    try:
        from weasyprint import HTML
        static_dir = os.path.join(current_app.root_path, "static")
        return HTML(string=html, base_url=static_dir).write_pdf()
    except Exception:
        pass

    # 3. Tertiary: xhtml2pdf
    from xhtml2pdf import pisa
    result = io.BytesIO()
    pisa.CreatePDF(src=html, dest=result, path=os.path.join(current_app.root_path, "static"))
    return result.getvalue()