"""
app/admin.py
────────────
Registrations admin panel — session login, the dashboard, and the status
update endpoint.

This deliberately does NOT roll its own CSRF protection or login rate
limiting: your app already has `csrf` (Flask-WTF) and `limiter`
(Flask-Limiter) wired up in extensions.py and initialised in create_app(),
so this file just uses those. `csrf_token()` is auto-registered as a Jinja
global by CSRFProtect, and `X-CSRFToken` / `X-CSRF-Token` are both accepted
headers by default — the fetch() calls in admin_registrations.html already
send the right one.

WIRE-UP CHECKLIST
  1. Add the AdminUser / Registration models to app/models.py (snippet
     provided separately — you already have IqamaSetting, Announcement,
     JummaCollection there, so this just adds two more classes).
  2. Run a migration:
         flask db migrate -m "add admin_users and registrations"
         flask db upgrade
  3. Register this blueprint in your app factory's _register_blueprints()
     (see the updated run.py).
  4. Add the session-cookie config lines to your Config class (snippet
     provided separately) — that's what makes the login session secure.
  5. Create your first admin login:
         flask admin create-admin youradminname
     (namespaced under "admin" because it's a blueprint CLI command)
  6. Drop admin_login.html and admin_registrations.html into
     app/templates/ (already there if you used the files as delivered).

FIXES IN THIS VERSION
  - The Urdu-transliteration route used to be declared at
    "/admin/registrations/urdu" *inside* a blueprint that already has
    url_prefix="/admin", so it actually lived at
    "/admin/admin/registrations/urdu" and 404'd every time. It's now
    "/registrations/urdu" (→ /admin/registrations/urdu), matches the
    front-end default, and is behind @login_required like every other
    admin route.
  - Added the /registrations/nikah/new and /registrations/madrasa/new
    POST endpoints the "Save Record" / "Submit" buttons in
    admin_registrations.html were already calling but that didn't exist
    yet, so those actions were 404ing silently.
"""
from datetime import datetime, date, time as dtime
from decimal import Decimal, InvalidOperation
from functools import wraps

import click
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, jsonify, flash, current_app
)

from app.extensions import db, limiter
from app.models import Admin as AdminUser, NikahApplication, MadrasaApplication, IqamaSetting
from app.services.prayer_times import PRAYER_ORDER, PRAYER_ARABIC

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            flash("Please log in to continue.", "error")
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@admin_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per 15 minutes", methods=["POST"])
def login():
    if session.get("admin_id"):
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = AdminUser.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session.clear()
            session["admin_id"] = user.id
            session["admin_username"] = user.username
            session.permanent = True
            return redirect(request.args.get("next") or url_for("admin.dashboard"))

        # Same message whether the username or password was wrong — don't
        # leak which one, that's a username-enumeration hole.
        flash("Incorrect username or password.", "error")

    return render_template("admin_login.html")


@admin_bp.route("/logout")
def logout():
    session.clear()
    flash("You've been logged out.", "success")
    return redirect(url_for("admin.login"))


@admin_bp.route("/registrations")
@login_required
def dashboard():
    nikah_rows = [r.to_row() for r in NikahApplication.query.order_by(NikahApplication.created_at.desc()).all()]
    madrasa_rows = [r.to_row() for r in MadrasaApplication.query.order_by(MadrasaApplication.created_at.desc()).all()]
    combined = sorted(nikah_rows + madrasa_rows, key=lambda row: row["submitted_at"], reverse=True)

    now = datetime.utcnow()
    # %-d (no-leading-zero day) isn't supported by strftime on Windows —
    # build the display string manually instead of formatting it in the template.
    today_display = now.strftime("%A, ") + str(now.day) + now.strftime(" %B %Y")
    return render_template(
        "admin_registrations.html",
        registrations=combined,
        mosque_name=current_app.config.get("MOSQUE_NAME", "Masjid"),
        today=now,
        today_display=today_display,
        admin_username=session.get("admin_username"),
        active_page="registrations",
    )


@admin_bp.route("/registrations/<string:reg_id>/status", methods=["POST"])
@login_required
def update_status(reg_id):
    payload = request.get_json(silent=True) or {}
    new_status = payload.get("status")
    if new_status not in ("pending", "contacted", "approved"):
        return jsonify({"error": "Invalid status"}), 400

    try:
        kind, numeric_id = reg_id.split("-", 1)
        numeric_id = int(numeric_id)
    except ValueError:
        return jsonify({"error": "Invalid registration id"}), 400

    if kind == "nikah":
        reg = NikahApplication.query.get_or_404(numeric_id)
    elif kind == "madrasa":
        reg = MadrasaApplication.query.get_or_404(numeric_id)
    else:
        return jsonify({"error": "Invalid registration id"}), 400

    reg.status = new_status
    db.session.commit()
    return jsonify({"ok": True, "id": reg_id, "status": new_status})


@admin_bp.route("/registrations/<string:reg_id>/delete", methods=["POST"])
@login_required
def delete_registration(reg_id):
    try:
        kind, numeric_id = reg_id.split("-", 1)
        numeric_id = int(numeric_id)
    except ValueError:
        return jsonify({"error": "Invalid registration id"}), 400

    if kind == "nikah":
        reg = NikahApplication.query.get_or_404(numeric_id)
    elif kind == "madrasa":
        reg = MadrasaApplication.query.get_or_404(numeric_id)
    else:
        return jsonify({"error": "Invalid registration id"}), 400

    db.session.delete(reg)
    db.session.commit()
    return jsonify({"ok": True, "id": reg_id})


def _set_from_payload(instance, table, data, skip=("id", "status", "created_at")):
    """Copy matching keys from a JSON payload onto a model instance, casting to
    each column's Python type where possible. Blank strings become NULL.
    Any value that fails to cast is left unset instead of raising a 500 —
    better a missing field than a broken save.
    """
    for column in table.columns:
        name = column.name
        if name in skip or name not in data:
            continue

        raw = data[name]
        if isinstance(raw, str):
            raw = raw.strip()
        if raw in ("", None):
            setattr(instance, name, None)
            continue

        try:
            py_type = column.type.python_type
        except NotImplementedError:
            py_type = None

        try:
            if py_type is int:
                value = int(raw)
            elif py_type in (float, Decimal):
                value = py_type(raw)
            elif py_type is date and isinstance(raw, str):
                value = datetime.strptime(raw, "%Y-%m-%d").date()
            elif py_type is dtime and isinstance(raw, str):
                h, m = raw.split(":")[:2]
                value = dtime(int(h), int(m))
            else:
                value = raw
        except (ValueError, InvalidOperation):
            continue

        setattr(instance, name, value)


@admin_bp.route("/registrations/nikah/new", methods=["POST"])
@login_required
def create_nikah():
    data = request.get_json(silent=True) or {}
    if not (data.get("contact") and data.get("nikah_date") and data.get("groom_name") and data.get("bride_name")):
        return jsonify({"error": "Missing required fields"}), 400

    reg = NikahApplication()
    _set_from_payload(reg, NikahApplication.__table__, data)
    if not getattr(reg, "status", None):
        reg.status = data.get("status") if data.get("status") in ("pending", "contacted", "approved") else "pending"

    db.session.add(reg)
    db.session.commit()

    row = reg.to_row()
    row["db_id"] = row["id"]
    return jsonify({"row": row}), 201


@admin_bp.route("/registrations/madrasa/new", methods=["POST"])
@login_required
def create_madrasa():
    data = request.get_json(silent=True) or {}
    if not (data.get("contact") and data.get("child_name") and data.get("parent_name")):
        return jsonify({"error": "Missing required fields"}), 400

    reg = MadrasaApplication()
    _set_from_payload(reg, MadrasaApplication.__table__, data)
    if not getattr(reg, "status", None):
        reg.status = data.get("status") if data.get("status") in ("pending", "contacted", "approved") else "pending"

    db.session.add(reg)
    db.session.commit()

    row = reg.to_row()
    row["db_id"] = row["id"]
    return jsonify({"row": row}), 201


@admin_bp.route("/users")
@login_required
def users():
    admins = AdminUser.query.order_by(AdminUser.username.asc()).all()
    return render_template(
        "admin_users.html",
        admins=admins,
        mosque_name=current_app.config.get("MOSQUE_NAME", "Masjid"),
        admin_username=session.get("admin_username"),
        current_admin_id=session.get("admin_id"),
        active_page="users",
    )


@admin_bp.route("/users/create", methods=["POST"])
@login_required
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not username or not password:
        flash("Username and password are required.", "error")
    elif len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
    elif password != confirm_password:
        flash("Passwords do not match.", "error")
    elif AdminUser.query.filter_by(username=username).first():
        flash(f"'{username}' is already taken.", "error")
    else:
        user = AdminUser(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"Admin '{username}' added.", "success")

    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:admin_id>/delete", methods=["POST"])
@login_required
def delete_user(admin_id):
    if admin_id == session.get("admin_id"):
        flash("You can't remove your own account while logged in.", "error")
        return redirect(url_for("admin.users"))

    if AdminUser.query.count() <= 1:
        flash("At least one admin account must remain.", "error")
        return redirect(url_for("admin.users"))

    user = AdminUser.query.get_or_404(admin_id)
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f"Admin '{username}' removed.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/prayer-times", methods=["GET", "POST"])
@login_required
def prayer_times():
    settings = {s.prayer_name: s for s in IqamaSetting.query.all()}
    for name in PRAYER_ORDER:
        if name not in settings:
            s = IqamaSetting(prayer_name=name, azan_source="api", mode="offset", offset_minutes=15)
            db.session.add(s)
            settings[name] = s
    db.session.commit()

    if request.method == "POST":
        had_error = False
        for name in PRAYER_ORDER:
            s = settings[name]

            azan_source = request.form.get(f"{name}_azan_source", "api")
            s.azan_source = azan_source if azan_source in ("api", "manual") else "api"

            if s.azan_source == "manual":
                raw = request.form.get(f"{name}_manual_azan_time", "").strip()
                try:
                    h, m = raw.split(":")
                    s.manual_azan_time = dtime(int(h), int(m))
                except (ValueError, AttributeError):
                    flash(f"Please enter a valid manual Azan time for {name}.", "error")
                    had_error = True
                    continue

            iqama_mode = request.form.get(f"{name}_iqama_mode", "offset")
            s.mode = iqama_mode if iqama_mode in ("offset", "fixed") else "offset"

            if s.mode == "offset":
                try:
                    s.offset_minutes = int(request.form.get(f"{name}_offset_minutes", 15))
                except ValueError:
                    flash(f"Please enter a valid Iqama offset (minutes) for {name}.", "error")
                    had_error = True
                    continue
            else:
                raw = request.form.get(f"{name}_fixed_time", "").strip()
                try:
                    h, m = raw.split(":")
                    s.fixed_time = dtime(int(h), int(m))
                except (ValueError, AttributeError):
                    flash(f"Please enter a valid fixed Iqama time for {name}.", "error")
                    had_error = True
                    continue

        db.session.commit()
        if not had_error:
            flash("Prayer time settings saved.", "success")
        return redirect(url_for("admin.prayer_times"))

    return render_template(
        "admin_prayer_times.html",
        settings=settings,
        prayer_order=PRAYER_ORDER,
        prayer_arabic=PRAYER_ARABIC,
        mosque_name=current_app.config.get("MOSQUE_NAME", "Masjid"),
        admin_username=session.get("admin_username"),
        active_page="prayer_times",
    )


@admin_bp.cli.command("create-admin")
@click.argument("username")
@click.password_option()
def create_admin(username, password):
    """flask admin create-admin <username> — create or reset an admin login.

    click.password_option() prompts for the password (with confirmation)
    instead of taking it as a plain CLI argument, so it never ends up in
    your shell history.
    """
    user = AdminUser.query.filter_by(username=username).first()
    if not user:
        user = AdminUser(username=username)
        db.session.add(user)
    user.set_password(password)
    db.session.commit()
    click.echo(f"Admin user '{username}' saved.")


# ─────────────────────────────────────────────────────────────────────────
# Urdu transliteration for the Nikah Nama form.
#
#   pip install google-genai
#   export GEMINI_API_KEY=...
#
# If you already have a Gemini client in the project, reuse it instead of
# creating _gemini here. The front end calls POST /admin/registrations/urdu
# by default — override with `urdu_endpoint=` in render_template() if needed.
# ─────────────────────────────────────────────────────────────────────────

import json
import os
import re

from google import genai

_gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")


def _extract_retry_seconds(message, default=30):
    """Google's quota errors embed a 'Please retry in 58.9s' style string —
    pull the number out so the client can wait exactly that long instead of
    guessing."""
    match = re.search(r"retry in (\d+(?:\.\d+)?)s", message, re.IGNORECASE)
    if match:
        try:
            return int(float(match.group(1))) + 1
        except ValueError:
            pass
    return default

URDU_PROMPT = """You convert English text from Indian Muslim marriage records into Urdu script.

Rules:
- Transliterate personal names phonetically, e.g. "Mohammed Ayaan Sheikh" -> "محمد ایان شیخ".
- For addresses: transliterate place names and translate common words
  (Road -> روڈ, Street -> اسٹریٹ, Near -> قریب, Building -> بلڈنگ, Mumbai -> ممبئی).
- Write numbers with Urdu digits (۰۱۲۳۴۵۶۷۸۹).
- No explanations, no quotes, no English left over.

Input is a JSON array of strings. Return a JSON array of Urdu strings of the same length and order.

Input:
"""


@admin_bp.route("/registrations/urdu", methods=["POST"])
@login_required
def urdu_transliterate():
    body = request.get_json(silent=True) or {}
    items = [str(x).strip()[:300] for x in (body.get("items") or [])][:40]
    if not items:
        return jsonify({"items": []})

    try:
        resp = _gemini.models.generate_content(
            model=GEMINI_MODEL,
            contents=URDU_PROMPT + json.dumps(items, ensure_ascii=False),
            config={"response_mime_type": "application/json", "temperature": 0},
        )
        out = json.loads(resp.text)
        if not (isinstance(out, list) and len(out) == len(items)):
            raise ValueError("Gemini returned a different number of items")
        return jsonify({"items": [str(x).strip() for x in out]})
    except Exception as exc:
        current_app.logger.exception("Urdu transliteration failed")
        message = str(exc)
        if "RESOURCE_EXHAUSTED" in message or "429" in message:
            # Free-tier quota hit — Google tells us exactly how long to wait.
            return jsonify({
                "error": "rate_limited",
                "retry_after": _extract_retry_seconds(message, default=30),
            }), 429
        if "UNAVAILABLE" in message or "503" in message:
            # Transient overload on Google's side, not a quota problem.
            return jsonify({"error": "overloaded", "retry_after": 8}), 503
        return jsonify({"error": "urdu_failed"}), 502