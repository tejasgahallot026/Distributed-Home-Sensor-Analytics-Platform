import logging
import os

from flask import Flask
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app(test_config=None):
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app = Flask(__name__, template_folder=os.path.join(root, "templates"))

    from app.config import DevelopmentConfig, ProductionConfig, resolve_sqlalchemy_database_uri

    env = os.environ.get("FLASK_ENV", "production")
    app.config.from_object(DevelopmentConfig if env == "development" else ProductionConfig)
    app.config["SQLALCHEMY_DATABASE_URI"] = resolve_sqlalchemy_database_uri()
    if test_config:
        app.config.update(test_config)
    if not app.config["SQLALCHEMY_DATABASE_URI"]:
        raise RuntimeError(
            "DATABASE_URL is not set. Point it at a PostgreSQL database, "
            "or set FLASK_ENV=development to use a local SQLite file."
        )

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db.init_app(app)
    CORS(app)

    from app.api import api_bp
    from app.dashboard import dashboard_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    with app.app_context():
        from app import models  # noqa: F401  (register tables)
        db.create_all()

    # Under Gunicorn, gunicorn.conf.py starts these after the worker forks
    # (threads do not survive a fork, which matters with --preload).
    if os.environ.get("BACKGROUND_SERVICES") != "post_fork":
        start_background_services(app)

    return app


def start_background_services(app):
    """Start the MQTT subscriber and/or demo simulator once per process."""
    if app.extensions.get("background_started"):
        return
    app.extensions["background_started"] = True

    if app.config.get("ENABLE_MQTT"):
        from app.mqtt_handler import MQTTHandler

        handler = MQTTHandler(app, app.config["MQTT_BROKER_URL"])
        app.extensions["mqtt"] = handler
        handler.start()

    if app.config.get("DEMO_MODE"):
        from app.demo import start_demo

        start_demo(app)
