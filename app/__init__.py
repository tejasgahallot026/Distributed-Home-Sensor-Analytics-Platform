from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
import os
import logging

db = SQLAlchemy()
migrate = Migrate()
mqtt_client = None

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.config.from_object('app.config.Config')
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app)
    
    # Logging
    logging.basicConfig(level=logging.INFO)
    app.logger.setLevel(logging.INFO)
    
    # Blueprints
    from app.api import api_bp
    from app.dashboard import dashboard_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(dashboard_bp)
    
    # MQTT Handler
    from app.mqtt_handler import MQTTHandler
    global mqtt_client
    mqtt_client = MQTTHandler(app.config['MQTT_BROKER_URL'])
    
    @app.before_first_request
    def startup():
        mqtt_client.connect()
    
    @app.teardown_appcontext
    def shutdown_mqtt(exception):
        if mqtt_client:
            mqtt_client.disconnect()
    
    return app
