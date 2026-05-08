import os
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def _dev_sqlite_uri():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    instance = os.path.join(root, "instance")
    os.makedirs(instance, exist_ok=True)
    path = os.path.join(instance, "dev.sqlite").replace("\\", "/")
    return "sqlite:///" + path


def normalize_database_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    uri = raw.replace("postgres://", "postgresql://", 1)
    parsed = urlparse(uri)
    if parsed.scheme.startswith("sqlite"):
        return uri
    if not parsed.scheme.startswith("postgres"):
        return uri
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if not any(k.lower() == "sslmode" for k, _ in pairs):
        pairs = list(pairs) + [("sslmode", "require")]
    query = urlencode(pairs)
    return urlunparse(parsed._replace(query=query))


def resolve_sqlalchemy_database_uri():
    raw = os.environ.get("DATABASE_URL", "").strip()
    if raw:
        return normalize_database_url(raw)
    if os.environ.get("FLASK_ENV") == "development":
        return _dev_sqlite_uri()
    return ""


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key-change-me"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    JSON_SORT_KEYS = False
    MQTT_BROKER_URL = os.environ.get("MQTT_BROKER_URL", "mqtt://localhost:1883")


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False


class ProductionConfig(Config):
    DEBUG = False
