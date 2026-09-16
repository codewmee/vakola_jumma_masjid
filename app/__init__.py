import logging
import os
import sys
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, jsonify, request

from config import get_config
from app.extensions import db, migrate, csrf, limiter


def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or get_config())

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY environment variable must be set. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    os.makedirs(app.instance_path, exist_ok=True)

    _configure_logging(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_security_headers(app)
    _register_cli(app)

    return app


def _configure_logging(app: Flask) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    app.logger.handlers = [handler]
    app.logger.setLevel(app.config.get("LOG_LEVEL", "INFO"))
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)


def _register_blueprints(app: Flask) -> None:
    from app.routes.main import main_bp
    from app.routes.api import api_bp
    from app.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_e):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Not found."}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def rate_limited(_e):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Too many requests. Please try again shortly."}), 429
        return render_template("errors/generic.html", message="Too many requests. Please try again shortly."), 429

    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Unhandled server error: %s", e)
        db.session.rollback()
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Something went wrong. Please try again."}), 500
        return render_template("errors/generic.html", message="Something went wrong. Please try again."), 500


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if app.config.get("PREFERRED_URL_SCHEME") == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


def _register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    def seed():
        """Populate the database with sensible defaults (Iqama times, sample notices)."""
        from app.seed import run_seed

        run_seed()
        print("Database seeded.")