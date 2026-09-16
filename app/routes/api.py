import re
from datetime import datetime, date

from flask import Blueprint, request, jsonify, current_app

from app.extensions import db, limiter
from app.models import NikahApplication, MadrasaApplication, Donation, PaymentStatus

api_bp = Blueprint("api", __name__, url_prefix="/api")

PHONE_RE = re.compile(r"^[\d+\-\s()]{7,20}$")


def _error(message, status=400, field=None):
    body = {"ok": False, "error": message}
    if field:
        body["field"] = field
    return jsonify(body), status


def _require_str(data, field, max_len=120, min_len=1):
    val = (data.get(field) or "").strip()
    if not (min_len <= len(val) <= max_len):
        return None, _error(f"'{field}' is required (max {max_len} characters).", field=field)
    return val, None


@api_bp.route("/nikah", methods=["POST"])
@limiter.limit("10 per hour")
def submit_nikah():
    data = request.get_json(silent=True) or {}

    bride_name, err = _require_str(data, "bride")
    if err:
        return err
    groom_name, err = _require_str(data, "groom")
    if err:
        return err
    contact, err = _require_str(data, "contact", max_len=30)
    if err:
        return err
    if not PHONE_RE.match(contact):
        return _error("Please enter a valid contact number.", field="contact")

    raw_date = (data.get("date") or "").strip()
    try:
        preferred_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return _error("Please choose a valid date.", field="date")
    if preferred_date < date.today():
        return _error("Preferred date cannot be in the past.", field="date")

    application = NikahApplication(
        bride_name=bride_name,
        groom_name=groom_name,
        preferred_date=preferred_date,
        contact_number=contact,
    )
    db.session.add(application)
    db.session.commit()

    current_app.logger.info("New Nikah application #%s submitted.", application.id)
    return jsonify({"ok": True, "message": "Your Nikah Nama application has been received. Jazakallah Khair."})


@api_bp.route("/madrasa", methods=["POST"])
@limiter.limit("10 per hour")
def submit_madrasa():
    data = request.get_json(silent=True) or {}

    child_name, err = _require_str(data, "name")
    if err:
        return err
    parent_name, err = _require_str(data, "parent")
    if err:
        return err
    contact, err = _require_str(data, "contact", max_len=30)
    if err:
        return err
    if not PHONE_RE.match(contact):
        return _error("Please enter a valid contact number.", field="contact")

    try:
        age = int(data.get("age"))
    except (TypeError, ValueError):
        return _error("Please enter a valid age.", field="age")
    if not (5 <= age <= 16):
        return _error("Madrasa admissions are open for ages 5 to 16.", field="age")

    application = MadrasaApplication(
        child_name=child_name,
        child_age=age,
        parent_name=parent_name,
        contact_number=contact,
    )
    db.session.add(application)
    db.session.commit()

    current_app.logger.info("New Madrasa application #%s submitted.", application.id)
    return jsonify({"ok": True, "message": "Enrolment received. We'll contact you shortly. Jazakallah Khair."})


@api_bp.route("/donate", methods=["POST"])
@limiter.limit("15 per hour")
def create_donation():
    """Creates a Donation record. If Razorpay is configured, also creates a
    Razorpay order and returns the order details for the client to open
    checkout with. Otherwise the donation is recorded as a 'pledge' and the
    mosque can follow up with the donor directly (bank transfer, in person).
    """
    data = request.get_json(silent=True) or {}

    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return _error("Please enter a valid amount.", field="amount")
    if amount < 1 or amount > 100000:
        return _error("Please enter an amount between 1 and 100,000.", field="amount")

    donor_name = (data.get("name") or "").strip()[:120] or None
    donor_email = (data.get("email") or "").strip()[:120] or None
    currency = current_app.config.get("DONATION_CURRENCY", "GBP")

    donation = Donation(
        donor_name=donor_name,
        donor_email=donor_email,
        amount=amount,
        currency=currency,
        payment_status=PaymentStatus.CREATED.value,
    )

    key_id = current_app.config.get("RAZORPAY_KEY_ID")
    key_secret = current_app.config.get("RAZORPAY_KEY_SECRET")

    if key_id and key_secret:
        try:
            import razorpay

            client = razorpay.Client(auth=(key_id, key_secret))
            order = client.order.create(
                {
                    "amount": int(round(amount * 100)),  # smallest currency unit
                    "currency": currency,
                    "payment_capture": 1,
                }
            )
            donation.razorpay_order_id = order["id"]
            db.session.add(donation)
            db.session.commit()
            return jsonify(
                {
                    "ok": True,
                    "mode": "razorpay",
                    "order_id": order["id"],
                    "amount": order["amount"],
                    "currency": order["currency"],
                    "key_id": key_id,
                    "donation_id": donation.id,
                }
            )
        except Exception as exc:  # noqa: BLE001
            current_app.logger.error("Razorpay order creation failed: %s", exc)
            return _error("Payment gateway is temporarily unavailable. Please try again shortly.", status=502)

    # No payment gateway configured — record as a pledge for manual follow-up.
    donation.payment_status = PaymentStatus.PLEDGED.value
    db.session.add(donation)
    db.session.commit()
    current_app.logger.info("New donation pledge #%s recorded (no gateway configured).", donation.id)
    return jsonify(
        {
            "ok": True,
            "mode": "pledge",
            "message": "Jazakallah Khair! Your pledge has been recorded — our team will contact you to complete payment.",
        }
    )


@api_bp.route("/donate/verify", methods=["POST"])
@limiter.limit("20 per hour")
def verify_donation():
    """Verifies a Razorpay payment signature after client-side checkout completes."""
    key_id = current_app.config.get("RAZORPAY_KEY_ID")
    key_secret = current_app.config.get("RAZORPAY_KEY_SECRET")
    if not (key_id and key_secret):
        return _error("Payment gateway is not configured.", status=400)

    data = request.get_json(silent=True) or {}
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")
    if not all([order_id, payment_id, signature]):
        return _error("Missing payment verification fields.")

    import razorpay

    client = razorpay.Client(auth=(key_id, key_secret))
    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }
        )
    except razorpay.errors.SignatureVerificationError:
        return _error("Payment verification failed.", status=400)

    donation = Donation.query.filter_by(razorpay_order_id=order_id).first()
    if donation is None:
        return _error("Donation record not found.", status=404)

    donation.razorpay_payment_id = payment_id
    donation.payment_status = PaymentStatus.PAID.value
    db.session.commit()

    current_app.logger.info("Donation #%s confirmed paid via Razorpay.", donation.id)
    return jsonify({"ok": True, "message": "Jazakallah Khair! Your donation has been received."})
