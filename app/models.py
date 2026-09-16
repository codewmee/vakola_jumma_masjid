from datetime import datetime, date, timedelta
from enum import Enum

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
