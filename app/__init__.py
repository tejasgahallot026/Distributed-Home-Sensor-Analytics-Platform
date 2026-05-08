import logging
import os
from threading import Thread

from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()


def create_app():
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")
    app = Flask(__name__, template_folder=template_dir)

    from app.config import DevelopmentConfig, ProductionConfig, resolve_sqlalchemy_database_uri

    env = os.environ.get("FLASK_ENV", "production")
    app.config.from_object(DevelopmentConfig if env == "development" else ProductionConfig)

    db_uri = resolve_sqlalchemy_database_uri()
    if not db_uri:
        raise RuntimeError(
            "DATABASE_URL is not set. In Render: Web Service → Environment → Link your PostgreSQL "
            "database (or add DATABASE_URL manually from the database's Connections tab)."
        )
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri

    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app)

    from app.api import api_bp
    from app.dashboard import dashboard_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()

    if os.environ.get("ENABLE_MQTT") == "1":
        try:
            from app.mqtt_handler import MQTTHandler

            handler = MQTTHandler(app.config["MQTT_BROKER_URL"])

            def run_mqtt():
                handler.connect()

            Thread(target=run_mqtt, daemon=True).start()
        except Exception:
            logging.exception("MQTT startup failed")

    return app
