"""Fetches daily prayer (Azan) times from the Aladhan API and combines them
with mosque-specific Iqama settings stored in the database. Either can be
overridden per prayer via IqamaSetting.azan_source ("api" | "manual").

The Aladhan API is free, keyless, and widely used for this purpose:
https://aladhan.com/prayer-times-api

If every prayer is set to "manual" Azan, the Aladhan API is never called at
all — useful if you haven't configured MOSQUE_LAT/MOSQUE_LNG yet, or simply
don't want to depend on it. Results are cached in-process for
PRAYER_TIMES_CACHE_SECONDS to avoid hammering the upstream API on every page
load. If the upstream call fails (network issue, rate limit, missing config,
etc.) we fall back to the last successfully cached value, and if none exists
yet, to a safe static default so the page never breaks.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, date, time as dtime
from typing import TypedDict
from zoneinfo import ZoneInfo

import requests
from flask import current_app

logger = logging.getLogger(__name__)

PRAYER_ORDER = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]
PRAYER_ARABIC = {
    "Fajr": "الفجر",
    "Dhuhr": "الظهر",
    "Asr": "العصر",
    "Maghrib": "المغرب",
    "Isha": "العشاء",
}

# Fallback used only if the Aladhan API is unreachable/unconfigured and no cache exists.
_FALLBACK_TIMES = {
    "Fajr": "05:12",
    "Dhuhr": "12:30",
    "Asr": "15:48",
    "Maghrib": "18:22",
    "Isha": "19:55",
}

_cache: dict = {"fetched_at": 0.0, "date": None, "timings": None}


class PrayerRow(TypedDict):
    name: str
    arabic: str
    time: str
    iqama: str
    active: bool


def _fetch_from_aladhan(for_date: date) -> dict | None:
    cfg = current_app.config
    try:
        base_url = cfg["ALADHAN_BASE_URL"]
        params = {
            "latitude": cfg["MOSQUE_LAT"],
            "longitude": cfg["MOSQUE_LNG"],
            "method": cfg["ALADHAN_METHOD"],
            "school": cfg["ALADHAN_SCHOOL"],
        }
        url = f"{base_url}/timings/{for_date.strftime('%d-%m-%Y')}"
        resp = requests.get(url, params=params, timeout=6)
        resp.raise_for_status()
        payload = resp.json()
        timings = payload["data"]["timings"]
        # Aladhan returns "HH:MM (TZ)" sometimes — strip anything after a space.
        return {k: v.split(" ")[0] for k, v in timings.items()}
    except (requests.RequestException, KeyError, ValueError) as exc:
        logger.warning("Aladhan API fetch failed or not configured: %s", exc)
        return None


def get_raw_timings(force_refresh: bool = False) -> tuple[dict, date]:
    """Returns (timings_dict, date) for today, using the in-process cache."""
    tz = ZoneInfo(current_app.config["MOSQUE_TIMEZONE"])
    today = datetime.now(tz).date()
    cache_seconds = current_app.config["PRAYER_TIMES_CACHE_SECONDS"]

    cache_fresh = (
        _cache["timings"] is not None
        and _cache["date"] == today
        and (time.time() - _cache["fetched_at"]) < cache_seconds
    )
    if cache_fresh and not force_refresh:
        return _cache["timings"], today

    timings = _fetch_from_aladhan(today)
    if timings is not None:
        _cache.update(fetched_at=time.time(), date=today, timings=timings)
        return timings, today

    # Upstream failed or isn't configured — serve stale cache if we have one, else static fallback.
    if _cache["timings"] is not None:
        logger.info("Serving stale cached prayer times after upstream failure.")
        return _cache["timings"], _cache["date"]

    logger.warning("No cache available — serving static fallback prayer times.")
    return dict(_FALLBACK_TIMES), today


def _parse_hhmm(value: str) -> dtime:
    h, m = value.split(":")
    return dtime(int(h), int(m))


def _compute_iqama(prayer_name: str, azan_time: dtime, setting) -> dtime:
    """setting is an IqamaSetting row, or None if not yet configured."""
    if setting is None:
        default_offsets = {"Fajr": 15, "Dhuhr": 15, "Asr": 12, "Maghrib": 5, "Isha": 15}
        offset = default_offsets.get(prayer_name, 15)
        total_minutes = azan_time.hour * 60 + azan_time.minute + offset
        return dtime((total_minutes // 60) % 24, total_minutes % 60)

    if setting.mode == "fixed" and setting.fixed_time is not None:
        return setting.fixed_time

    total_minutes = azan_time.hour * 60 + azan_time.minute + setting.offset_minutes
    return dtime((total_minutes // 60) % 24, total_minutes % 60)


def get_today_prayers() -> list[PrayerRow]:
    """Returns the 5 daily prayers with Azan + Iqama times, current one flagged active."""
    from app.models import IqamaSetting

    settings = {s.prayer_name: s for s in IqamaSetting.query.all()}

    # Only hit the Aladhan API if at least one prayer actually needs it —
    # prayers with no setting yet default to "api" (back-compat), so an
    # unconfigured mosque still gets automatic times until they customise.
    needs_api = any(
        settings.get(name) is None or settings[name].azan_source != "manual"
        for name in PRAYER_ORDER
    )
    timings: dict = {}
    if needs_api:
        timings, _ = get_raw_timings()

    tz = ZoneInfo(current_app.config["MOSQUE_TIMEZONE"])
    now = datetime.now(tz).time()

    rows: list[PrayerRow] = []
    for name in PRAYER_ORDER:
        setting = settings.get(name)

        if setting is not None and setting.azan_source == "manual" and setting.manual_azan_time is not None:
            azan_time = setting.manual_azan_time
        else:
            azan_str = timings.get(name, _FALLBACK_TIMES[name])
            azan_time = _parse_hhmm(azan_str)

        iqama_time = _compute_iqama(name, azan_time, setting)
        rows.append(
            PrayerRow(
                name=name,
                arabic=PRAYER_ARABIC[name],
                time=azan_time.strftime("%H:%M"),
                iqama=iqama_time.strftime("%H:%M"),
                active=False,
            )
        )

    # Mark the next upcoming prayer as active; if past Isha, Fajr (tomorrow) is next.
    next_index = None
    for i, row in enumerate(rows):
        if _parse_hhmm(row["time"]) >= now:
            next_index = i
            break
    if next_index is None:
        next_index = 0  # past Isha — next prayer is tomorrow's Fajr
    rows[next_index]["active"] = True

    return rows


def get_next_prayer() -> PrayerRow:
    for row in get_today_prayers():
        if row["active"]:
            return row
    raise RuntimeError("No active prayer found — this should never happen.")