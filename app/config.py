# NOTE: I don't have your original config.py — only the snippet I gave you
# last time (the SESSION_* lines below), which looks like it ended up
# replacing the whole file instead of being merged into it. This rebuilds
# a Config/get_config() using the settings your codebase already references
# (SECRET_KEY, SQLALCHEMY_DATABASE_URI, LOG_LEVEL, PREFERRED_URL_SCHEME).
# If your original had more in it — Razorpay keys, mail settings, Cloudinary,
# a specific DB URL — re-add those here, I have no record of them.

import os
from datetime import timedelta


class Config:
    """Base config — shared across all environments."""

    SECRET_KEY = os.environ.get("SECRET_KEY")

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "http")

    MOSQUE_NAME = os.environ.get("MOSQUE_NAME", "Masjid")

    # Session cookie hardening — this is what makes the admin login secure.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # overridden to True in ProductionConfig
    PERMANENT_SESSION_LIFETIME = timedelta(hours=4)

    # Uncomment once Flask-Limiter needs to share state across workers:
    # RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI")


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    PREFERRED_URL_SCHEME = "https"
    SESSION_COOKIE_SECURE = True


_ENV_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config():
    env = os.environ.get("FLASK_ENV", os.environ.get("APP_ENV", "development")).lower()
    return _ENV_MAP.get(env, DevelopmentConfig)