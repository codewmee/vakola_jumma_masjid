"""Events: listing page, highlight photos, and Participate / Volunteer signups.

Save as app/routes/events.py and register in _register_blueprints():

    from app.routes.events import events_bp
    app.register_blueprint(events_bp)

Then create the tables (flask db migrate && flask db upgrade) and optionally
seed sample data with:  flask events seed
"""
import re
from datetime import date, datetime

from flask import Blueprint, current_app, jsonify, render_template, request

from app.extensions import db, limiter

events_bp = Blueprint("events", __name__)

PHONE_RE = re.compile(r"^[\d+\-\s()]{7,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# URL slug -> stored value
SIGNUP_KINDS = {"participate": "participant", "volunteer": "volunteer"}


# ─── MODELS ─────────────────────────────────────────────────────────────────
class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    category = db.Column(db.String(60), nullable=True)  # lecture, class, iftar...
    event_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.String(20), nullable=True)  # e.g. "19:30"
    location = db.Column(db.String(200), nullable=True)
    cover_url = db.Column(db.String(500), nullable=True)
    is_published = db.Column(db.Boolean, nullable=False, default=True)
    allow_participate = db.Column(db.Boolean, nullable=False, default=True)
    allow_volunteer = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    photos = db.relationship(
        "EventPhoto",
        backref="event",
        order_by="EventPhoto.id",
        cascade="all, delete-orphan",
    )
    signups = db.relationship(
        "EventSignup", backref="event", cascade="all, delete-orphan"
    )

    @property
    def is_upcoming(self):
        return self.event_date >= date.today()


class EventPhoto(db.Model):
    __tablename__ = "event_photos"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(160), nullable=True)   # shown on the highlight; falls back to caption, then event title
    photo_date = db.Column(db.Date, nullable=True)     # shown on the highlight; falls back to the event date
    caption = db.Column(db.String(200), nullable=True)


class EventSignup(db.Model):
    __tablename__ = "event_signups"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.Integer, db.ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = db.Column(db.String(20), nullable=False)  # participant | volunteer
    name = db.Column(db.String(120), nullable=False)
    contact_number = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    guests = db.Column(db.Integer, nullable=False, default=1)
    note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("event_id", "kind", "contact_number", name="uq_event_kind_contact"),
    )


# ─── HELPERS ────────────────────────────────────────────────────────────────
def _site_context():
    cfg = current_app.config
    return {
        "mosque_name": cfg.get("MOSQUE_NAME", "Masjid"),
        "mosque_address": cfg.get("MOSQUE_ADDRESS", ""),
        "mosque_phone": cfg.get("MOSQUE_PHONE", ""),
        "mosque_email": cfg.get("MOSQUE_EMAIL", ""),
        "currency_symbol": cfg.get("CURRENCY_SYMBOL", ""),
        "today": date.today(),
    }


def _error(message, status=400, field=None):
    body = {"ok": False, "error": message}
    if field:
        body["field"] = field
    return jsonify(body), status


# ─── ROUTES ─────────────────────────────────────────────────────────────────
@events_bp.route("/events")
def index():
    today = date.today()
    published = Event.query.filter(Event.is_published.is_(True))

    upcoming = (
        published.filter(Event.event_date >= today)
        .order_by(Event.event_date.asc(), Event.id.asc())
        .all()
    )
    # Highlights = past events that have photos
    past = (
        published.filter(Event.event_date < today)
        .order_by(Event.event_date.desc(), Event.id.desc())
        .limit(12)
        .all()
    )
    highlights = [e for e in past if e.photos]

    return render_template(
        "events.html", upcoming=upcoming, highlights=highlights, **_site_context()
    )


@events_bp.route("/events/<int:event_id>/<kind>", methods=["POST"])
@limiter.limit("10 per hour")
def signup(event_id, kind):
    if kind not in SIGNUP_KINDS:
        return _error("Unknown signup type.", status=404)

    event = Event.query.filter_by(id=event_id, is_published=True).first()
    if event is None:
        return _error("Event not found.", status=404)
    if not event.is_upcoming:
        return _error("This event has already taken place.")
    if kind == "participate" and not event.allow_participate:
        return _error("Participation is not open for this event.")
    if kind == "volunteer" and not event.allow_volunteer:
        return _error("Volunteering is not open for this event.")

    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    if not (1 <= len(name) <= 120):
        return _error("Please enter your name (max 120 characters).", field="name")

    contact = (data.get("contact") or "").strip()
    if not PHONE_RE.match(contact):
        return _error("Please enter a valid contact number.", field="contact")

    email = (data.get("email") or "").strip()[:120] or None
    if email and not EMAIL_RE.match(email):
        return _error("Please enter a valid email address.", field="email")

    guests = 1
    if kind == "participate":
        try:
            guests = int(data.get("guests") or 1)
        except (TypeError, ValueError):
            return _error("Please enter a valid number of people.", field="guests")
        if not (1 <= guests <= 10):
            return _error("You can register 1 to 10 people at a time.", field="guests")

    note = (data.get("note") or "").strip()[:500] or None

    exists = EventSignup.query.filter_by(
        event_id=event.id, kind=SIGNUP_KINDS[kind], contact_number=contact
    ).first()
    if exists:
        return _error("This number is already registered for this event.", field="contact")

    db.session.add(
        EventSignup(
            event_id=event.id,
            kind=SIGNUP_KINDS[kind],
            name=name,
            contact_number=contact,
            email=email,
            guests=guests,
            note=note,
        )
    )
    db.session.commit()

    current_app.logger.info("New %s signup for event #%s.", SIGNUP_KINDS[kind], event.id)
    message = (
        "You're registered. Jazakallah Khair!"
        if kind == "participate"
        else "Thank you for volunteering. We'll contact you soon. Jazakallah Khair!"
    )
    return jsonify({"ok": True, "message": message})


# ─── CLI: flask events seed ─────────────────────────────────────────────────
@events_bp.cli.command("seed")
def seed_events():
    """Insert sample events (only if the events table is empty)."""
    if Event.query.first():
        print("Events already exist. Nothing seeded.")
        return

    from datetime import timedelta

    t = date.today()
    img = "https://images.unsplash.com/{}?w=1000&h=700&fit=crop&auto=format"
    mosque = img.format("photo-1540567736792-f78f6242e4e0")
    ceiling = img.format("photo-1758696642915-996112fc0bae")
    crowd = img.format("photo-1600298881974-6be191ceeda1")

    upcoming = Event(
        title="Community Iftar & Lecture",
        description="Break the fast together followed by a short talk on gratitude.",
        category="Community",
        event_date=t + timedelta(days=10),
        start_time="18:30",
        location="Main Hall",
        cover_url=crowd,
    )
    upcoming2 = Event(
        title="Weekend Quran Class for Youth",
        description="Tajweed and reflection for ages 12 to 18.",
        category="Class",
        event_date=t + timedelta(days=17),
        start_time="10:00",
        location="Madrasa Room 2",
        cover_url=ceiling,
    )
    past = Event(
        title="Eid Milan Gathering",
        description="Families, food and games in the courtyard.",
        category="Festival",
        event_date=t - timedelta(days=30),
        start_time="11:00",
        location="Courtyard",
        cover_url=mosque,
    )
    past.photos = [
        EventPhoto(url=mosque, title="Morning prayer", photo_date=t - timedelta(days=30)),
        EventPhoto(url=crowd, title="Community lunch", photo_date=t - timedelta(days=29)),
        EventPhoto(url=ceiling, title="Main hall", photo_date=t - timedelta(days=28)),
    ]
    db.session.add_all([upcoming, upcoming2, past])
    db.session.commit()
    print("Seeded 3 events.")