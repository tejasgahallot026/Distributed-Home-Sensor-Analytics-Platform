import os


def _database_uri_from_env():
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        return ""
    uri = raw.replace("postgres://", "postgresql://", 1)
    if uri.startswith("sqlite"):
        return uri
    if "postgresql" in uri and "sslmode=" not in uri.lower():
        sep = "&" if "?" in uri else "?"
        uri = f"{uri}{sep}sslmode=require"
    return uri


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-me'
    SQLALCHEMY_DATABASE_URI = _database_uri_from_env()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    JSON_SORT_KEYS = False
    MQTT_BROKER_URL = os.environ.get('MQTT_BROKER_URL', 'mqtt://localhost:1883')

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False

class ProductionConfig(Config):
    DEBUG = False
