from datetime import time as dtime

from app.extensions import db
from app.models import IqamaSetting, Announcement, JummaCollection


DEFAULT_IQAMA = [
    # prayer_name, mode, offset_minutes, fixed_time
    ("Fajr", "offset", 15, None),
    ("Dhuhr", "offset", 15, None),
    ("Asr", "offset", 12, None),
    ("Maghrib", "offset", 5, None),
    ("Isha", "offset", 15, None),
    ("Jumma", "fixed", 0, dtime(13, 45)),
]

DEFAULT_ANNOUNCEMENTS = [
    ("📿", "Quran recitation circle — every Saturday after Fajr", 1),
    ("🌙", "Ramadan preparations meeting — check notice board for date", 2),
    ("📚", "Islamic studies for youth — Sundays 2–4 PM", 3),
]


def run_seed():
    for name, mode, offset, fixed in DEFAULT_IQAMA:
        existing = IqamaSetting.query.filter_by(prayer_name=name).first()
        if existing:
            continue
        db.session.add(
            IqamaSetting(prayer_name=name, mode=mode, offset_minutes=offset, fixed_time=fixed)
        )

    if Announcement.query.count() == 0:
        for icon, text, order in DEFAULT_ANNOUNCEMENTS:
            db.session.add(Announcement(icon=icon, text=text, sort_order=order))

    db.session.commit()
