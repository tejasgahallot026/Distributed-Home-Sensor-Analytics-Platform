import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL').replace("postgres://", "postgresql://") if os.environ.get('DATABASE_URL') else 'sqlite:///sensors.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MQTT_BROKER_URL = os.environ.get('MQTT_BROKER_URL', 'mqtt://mosquitto:1883')
