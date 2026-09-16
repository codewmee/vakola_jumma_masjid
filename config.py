import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


def _bool(env_val, default=False):
    if env_val is None:
        return default
    return env_val.strip().lower() in ("1", "true", "yes", "on")


class Config:
    """Base config — shared by all environments."""

    SECRET_KEY = os.environ.get("SECRET_KEY")

    # --- Database (Neon Postgres) ---
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "").replace(
        "postgres://", "postgresql+psycopg2://", 1
    ) or "sqlite:///" + os.path.join(basedir, "instance", "dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # --- Security ---
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_HEADERS = ["X-CSRFToken", "X-CSRF-Token"]
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=6)

    # --- Rate limiting ---
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = "200 per hour"

    # --- Mosque / site settings ---
    MOSQUE_NAME = os.environ.get("MOSQUE_NAME", "Vakola Jumma Masjid")
    MOSQUE_LAT = float(os.environ.get("MOSQUE_LAT", "19.0896"))
    MOSQUE_LNG = float(os.environ.get("MOSQUE_LNG", "72.8656"))
    MOSQUE_TIMEZONE = os.environ.get("MOSQUE_TIMEZONE", "Asia/Kolkata")
    # Aladhan calculation method: 1=Karachi(Hanafi-friendly for South Asia), see aladhan.com/calculation-methods
    ALADHAN_METHOD = int(os.environ.get("ALADHAN_METHOD", "1"))
    ALADHAN_SCHOOL = int(os.environ.get("ALADHAN_SCHOOL", "1"))  # 1 = Hanafi (Asr)
    ALADHAN_BASE_URL = os.environ.get("ALADHAN_BASE_URL", "https://api.aladhan.com/v1")
    PRAYER_TIMES_CACHE_SECONDS = int(os.environ.get("PRAYER_TIMES_CACHE_SECONDS", "3600"))

    MOSQUE_ADDRESS = os.environ.get("MOSQUE_ADDRESS", "Vakola, Santa Cruz East, Mumbai, 400055")
    MOSQUE_EMAIL = os.environ.get("MOSQUE_EMAIL", "info@vakolajummamasjid.org")
    MOSQUE_PHONE = os.environ.get("MOSQUE_PHONE", "+91 22 0000 0000")
    MONTHLY_JUMMA_GOAL = float(os.environ.get("MONTHLY_JUMMA_GOAL", "6000"))
    CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "£")
    DONATION_CURRENCY = os.environ.get("DONATION_CURRENCY", "GBP")  # ISO 4217 code, used by Razorpay

    # --- Razorpay (optional — donations fall back to "pledge" mode if unset) ---
    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")

    # --- Mail (optional notifications for new applications) ---
    ADMIN_NOTIFICATION_EMAIL = os.environ.get("ADMIN_NOTIFICATION_EMAIL")

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = Config.SECRET_KEY or "dev-only-insecure-key-change-me"
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config():
    env = os.environ.get("FLASK_ENV", "production")
    return config_by_name.get(env, ProductionConfig)
