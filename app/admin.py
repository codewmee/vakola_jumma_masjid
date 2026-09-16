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
headers by default — the fetch() call in admin_registrations.html already
sends the right one.

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
"""

from datetime import datetime
from functools import wraps

import click
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, jsonify, flash, current_app
)

from app.extensions import db, limiter
from app.models import AdminUser, Registration

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
    regs = Registration.query.order_by(Registration.submitted_at.desc()).all()
    return render_template(
        "admin_registrations.html",
        registrations=[r.to_row() for r in regs],
        mosque_name=current_app.config.get("MOSQUE_NAME", "Masjid"),
        today=datetime.utcnow(),
        admin_username=session.get("admin_username"),
    )


@admin_bp.route("/registrations/<int:reg_id>/status", methods=["POST"])
@login_required
def update_status(reg_id):
    payload = request.get_json(silent=True) or {}
    new_status = payload.get("status")
    if new_status not in ("pending", "contacted", "approved"):
        return jsonify({"error": "Invalid status"}), 400

    reg = Registration.query.get_or_404(reg_id)
    reg.status = new_status
    db.session.commit()
    return jsonify({"ok": True, "id": reg_id, "status": new_status})


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