from datetime import datetime, date, timedelta
from enum import Enum

from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


class ApplicationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class PaymentStatus(str, Enum):
    CREATED = "created"
    PAID = "paid"
    FAILED = "failed"
    PLEDGED = "pledged"  # no payment gateway configured — recorded as intent only


class RegistrationStatus(str, Enum):
    PENDING = "pending"
    CONTACTED = "contacted"
    APPROVED = "approved"


class RegistrationKind(str, Enum):
    NIKAH = "nikah"
    MADRASA = "madrasa"


class IqamaSetting(db.Model):
    """Mosque-specific Iqama (congregation) time per prayer.

    mode="offset": iqama = azan time + offset_minutes
    mode="fixed":  iqama = fixed_time (ignores azan time), e.g. Jumu'ah salah
    """

    __tablename__ = "iqama_settings"

    id = db.Column(db.Integer, primary_key=True)
    prayer_name = db.Column(db.String(20), unique=True, nullable=False)
    mode = db.Column(db.String(10), nullable=False, default="offset")
    offset_minutes = db.Column(db.Integer, nullable=False, default=15)
    fixed_time = db.Column(db.Time, nullable=True)

    def __repr__(self):
        return f"<IqamaSetting {self.prayer_name}>"


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    icon = db.Column(db.String(8), default="📿")
    text = db.Column(db.String(280), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Announcement {self.text[:30]!r}>"


class JummaCollection(db.Model):
    """One row per Jumu'ah (Friday) collection amount."""

    __tablename__ = "jumma_collections"

    id = db.Column(db.Integer, primary_key=True)
    collection_date = db.Column(db.Date, nullable=False, unique=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @staticmethod
    def week_start(d: date) -> date:
        return d - timedelta(days=d.weekday())

    def __repr__(self):
        return f"<JummaCollection {self.collection_date} {self.amount}>"


class NikahApplication(db.Model):
    __tablename__ = "nikah_applications"

    id = db.Column(db.Integer, primary_key=True)
    bride_name = db.Column(db.String(120), nullable=False)
    groom_name = db.Column(db.String(120), nullable=False)
    preferred_date = db.Column(db.Date, nullable=False)
    contact_number = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(20), default=ApplicationStatus.PENDING.value, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_row(self) -> dict:
        """Shape expected by admin_registrations.html. db_id is prefixed
        with the table name so the admin status-update route can tell
        nikah rows apart from madrasa rows sharing the same numeric id.
        """
        display_time = self.created_at.strftime("%I:%M %p")
        if display_time.startswith("0"):
            display_time = display_time[1:]
        return {
            "id": f"NIK-{self.id:04d}",
            "db_id": f"nikah-{self.id}",
            "type": "nikah",
            "status": self.status,
            "submitted_at": self.created_at.isoformat(),
            "display_date": f"{self.created_at.day} {self.created_at.strftime('%b %Y')}",
            "display_time": display_time,
            "bride": self.bride_name,
            "groom": self.groom_name,
            "nikah_date": self.preferred_date.isoformat() if self.preferred_date else "",
            "contact": self.contact_number,
        }

    def __repr__(self):
        return f"<NikahApplication {self.bride_name} & {self.groom_name}>"


class MadrasaApplication(db.Model):
    __tablename__ = "madrasa_applications"

    id = db.Column(db.Integer, primary_key=True)
    child_name = db.Column(db.String(120), nullable=False)
    child_age = db.Column(db.Integer, nullable=False)
    parent_name = db.Column(db.String(120), nullable=False)
    contact_number = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(20), default=ApplicationStatus.PENDING.value, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_row(self) -> dict:
        """Shape expected by admin_registrations.html. db_id is prefixed
        with the table name so the admin status-update route can tell
        madrasa rows apart from nikah rows sharing the same numeric id.
        """
        display_time = self.created_at.strftime("%I:%M %p")
        if display_time.startswith("0"):
            display_time = display_time[1:]
        return {
            "id": f"MAD-{self.id:04d}",
            "db_id": f"madrasa-{self.id}",
            "type": "madrasa",
            "status": self.status,
            "submitted_at": self.created_at.isoformat(),
            "display_date": f"{self.created_at.day} {self.created_at.strftime('%b %Y')}",
            "display_time": display_time,
            "child_name": self.child_name,
            "child_age": self.child_age,
            "parent_name": self.parent_name,
            "madrasa_contact": self.contact_number,
        }

    def __repr__(self):
        return f"<MadrasaApplication {self.child_name}>"


class Donation(db.Model):
    __tablename__ = "donations"

    id = db.Column(db.Integer, primary_key=True)
    donor_name = db.Column(db.String(120), nullable=True)
    donor_email = db.Column(db.String(120), nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), default="GBP", nullable=False)
    payment_status = db.Column(db.String(20), default=PaymentStatus.CREATED.value, nullable=False)
    razorpay_order_id = db.Column(db.String(64), nullable=True)
    razorpay_payment_id = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Donation {self.amount} {self.currency} {self.payment_status}>"


class Admin(db.Model):
    """Admin-panel login account. Password is never stored in plain text —
    use set_password()/check_password(), never assign password_hash directly.
    """

    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<Admin {self.username}>"


class Registration(db.Model):
    """Unified feed for the admin dashboard, covering both Nikah and
    Madrasa submissions via `kind`. Populated by the form-submission
    routes in app/routes/api.py — if those currently write only to
    NikahApplication/MadrasaApplication, update them to also (or
    instead) create a Registration row so the admin panel has data.
    """

    __tablename__ = "registrations"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False)  # RegistrationKind: "nikah" | "madrasa"

    # Nikah: bride_name/groom_name. Madrasa: child_name/parent_name.
    # Kept generic so one table serves both forms.
    primary_name = db.Column(db.String(120), nullable=False)
    secondary_name = db.Column(db.String(120), nullable=True)

    contact_number = db.Column(db.String(30), nullable=False)
    preferred_date = db.Column(db.Date, nullable=True)  # nikah only
    age = db.Column(db.Integer, nullable=True)  # madrasa only

    status = db.Column(db.String(20), default=RegistrationStatus.PENDING.value, nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_row(self) -> dict:
        """Shape expected by admin_registrations.html: 'id' is the display
        label (REG-0001), 'db_id' is the real primary key used by the
        status-update fetch() call, and nikah/madrasa fields are split out
        under the exact keys the template reads (bride/groom/... vs
        child_name/parent_name/...).
        """
        # %-d isn't supported by strftime on Windows, so build the
        # no-leading-zero day manually instead of relying on that flag.
        display_time = self.submitted_at.strftime("%I:%M %p")
        if display_time.startswith("0"):
            display_time = display_time[1:]

        row = {
            "id": f"REG-{self.id:04d}",
            "db_id": self.id,
            "type": self.kind,
            "status": self.status,
            "submitted_at": self.submitted_at.isoformat(),
            "display_date": f"{self.submitted_at.day} {self.submitted_at.strftime('%b %Y')}",
            "display_time": display_time,
        }

        if self.kind == RegistrationKind.NIKAH.value:
            row.update({
                "bride": self.primary_name,
                "groom": self.secondary_name,
                "nikah_date": self.preferred_date.isoformat() if self.preferred_date else "",
                "contact": self.contact_number,
            })
        else:
            row.update({
                "child_name": self.primary_name,
                "child_age": self.age,
                "parent_name": self.secondary_name,
                "madrasa_contact": self.contact_number,
            })

        return row

    def __repr__(self):
        return f"<Registration {self.kind} {self.primary_name!r} {self.status}>"