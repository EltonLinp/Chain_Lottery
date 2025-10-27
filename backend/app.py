from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from .config import load_settings
from .db import engine, session_scope
from .models import Base, SystemState
from .routes.admin import bp as admin_bp
from .routes.health import bp as health_bp
from .routes.tickets import bp as tickets_bp
from .routes.config import bp as config_bp

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def ensure_schema() -> None:
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("tickets")}
    statements = []
    if "buyer" not in columns:
        statements.append("ALTER TABLE tickets ADD COLUMN buyer VARCHAR(64)")
    if "tx_hash" not in columns:
        statements.append("ALTER TABLE tickets ADD COLUMN tx_hash VARCHAR(66)")

    if statements:
        try:
            with engine.begin() as conn:
                for stmt in statements:
                    conn.execute(text(stmt))
        except SQLAlchemyError:
            # In case the column already exists or the database does not support ALTER TABLE,
            # we silently ignore the failure to keep startup resilient.
            pass


def create_app() -> Flask:
    settings = load_settings()
    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.flask.secret_key
    Base.metadata.create_all(engine)
    ensure_schema()
    with session_scope() as session:
        state = session.get(SystemState, 1)
        if state is None:
            session.add(SystemState(id=1, current_period=1))

    app.register_blueprint(health_bp)
    app.register_blueprint(tickets_bp, url_prefix="/tickets")
    app.register_blueprint(admin_bp, url_prefix="/admin/api")
    app.register_blueprint(config_bp)

    @app.get("/")
    def serve_index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/assets/<path:filename>")
    def serve_assets(filename: str):
        return send_from_directory(FRONTEND_DIR / "assets", filename)

    @app.get("/admin")
    def serve_admin():
        return send_from_directory(FRONTEND_DIR, "admin.html")

    @app.errorhandler(Exception)
    def handle_error(exc: Exception):
        app.logger.exception("Unhandled error: %s", exc)
        return jsonify({"error": str(exc)}), 500

    return app
