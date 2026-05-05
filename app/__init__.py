from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
import os
import logging
from contextlib import contextmanager

db = SQLAlchemy()
migrate = Migrate()
mqtt_client = None

@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    try:
        yield db.session
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    finally:
        db.session.close()

def create_app(test_config=None):
    app = Flask(__name__)
    
    # Config
    config_name = os.environ.get('FLASK_ENV', 'production')
    app.config.from_object(f'app.config.{config_name.title()}Config')
    
    if test_config:
        app.config.update(test_config)
    
    # Extensions
    db.init_app(app)
    CORS(app)
    
    # Logging
    logging.basicConfig(level=logging.INFO)
    app.logger.setLevel(logging.INFO)
    
    # Blueprints
    from app.api import api_bp
    from app.dashboard import dashboard_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(dashboard_bp)
    
    # Create tables if they don't exist
    with app.app_context():
        db.create_all()
        app.logger.info("Database tables created/initialized")
    
    # Health check
    @app.route('/health')
    def health():
        return {'status': 'healthy', 'db': db.engine.has_table('sensor_reading')}
    
    # MQTT (disabled initially for stability)
    # from app.mqtt_handler import MQTTHandler
    # global mqtt_client
    # mqtt_client = MQTTHandler(app.config.get('MQTT_BROKER_URL', 'mqtt://localhost:1883'))
    
    app.logger.info(f"🚀 App initialized in {config_name} mode")
    return app
