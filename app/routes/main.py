from datetime import date, timedelta

from flask import Blueprint, render_template, current_app
from sqlalchemy import func, extract

from app.extensions import db
from app.models import Announcement, JummaCollection
from app.services.prayer_times import get_today_prayers

main_bp = Blueprint("main", __name__)


def _jumma_stats():
    cfg = current_app.config
    today = date.today()
    this_week_start = JummaCollection.week_start(today)
    last_week_start = this_week_start - timedelta(days=7)

    def sum_for(start=None, end=None, month=None, year=None):
        q = db.session.query(func.coalesce(func.sum(JummaCollection.amount), 0))
        if month and year:
            q = q.filter(
                extract("month", JummaCollection.collection_date) == month,
                extract("year", JummaCollection.collection_date) == year,
            )
        else:
            q = q.filter(JummaCollection.collection_date >= start)
            if end:
                q = q.filter(JummaCollection.collection_date < end)
        return float(q.scalar() or 0)

    this_week = sum_for(start=this_week_start)
    last_week = sum_for(start=last_week_start, end=this_week_start)
    this_month = sum_for(month=today.month, year=today.year)
    goal = cfg["MONTHLY_JUMMA_GOAL"]
    percent = min(100, round((this_month / goal) * 100)) if goal else 0

    symbol = cfg["CURRENCY_SYMBOL"]
    return {
        "this_week": f"{symbol} {this_week:,.0f}",
        "last_week": f"{symbol} {last_week:,.0f}",
        "this_month": f"{symbol} {this_month:,.0f}",
        "goal": f"{symbol} {goal:,.0f}",
        "percent": percent,
    }


@main_bp.route("/")
def index():
    prayers = get_today_prayers()
    notices = (
        Announcement.query.filter_by(is_active=True)
        .order_by(Announcement.sort_order.asc(), Announcement.created_at.desc())
        .limit(6)
        .all()
    )
    jumma = _jumma_stats()
    razorpay_enabled = bool(
        current_app.config.get("RAZORPAY_KEY_ID") and current_app.config.get("RAZORPAY_KEY_SECRET")
    )
    return render_template(
        "index.html",
        prayers=prayers,
        notices=notices,
        jumma=jumma,
        today=date.today(),
        mosque_name=current_app.config["MOSQUE_NAME"],
        mosque_address=current_app.config["MOSQUE_ADDRESS"],
        mosque_email=current_app.config["MOSQUE_EMAIL"],
        mosque_phone=current_app.config["MOSQUE_PHONE"],
        currency_symbol=current_app.config["CURRENCY_SYMBOL"],
        razorpay_enabled=razorpay_enabled,
        razorpay_key_id=current_app.config.get("RAZORPAY_KEY_ID"),
    )


@main_bp.route("/healthz")
def healthz():
    """Liveness/readiness probe for load balancers and container orchestrators."""
    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001 — health check must never raise
        db_ok = False
    status = 200 if db_ok else 503
    return {"status": "ok" if db_ok else "degraded", "database": db_ok}, status