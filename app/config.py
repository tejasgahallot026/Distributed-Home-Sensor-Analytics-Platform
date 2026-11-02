import os
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Hosts that mean "a database on this machine or in this Docker network",
# where Postgres normally runs without SSL.
LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "postgres"}


def _dev_sqlite_uri():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    instance = os.path.join(root, "instance")
    os.makedirs(instance, exist_ok=True)
    return "sqlite:///" + os.path.join(instance, "dev.sqlite").replace("\\", "/")


def normalize_database_url(raw: str) -> str:
    """Accept postgres:// URLs and require SSL only for remote databases.

    DATABASE_SSLMODE overrides the automatic choice (e.g. "disable" or "require").
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    uri = raw.replace("postgres://", "postgresql://", 1)
    parsed = urlparse(uri)
    if not parsed.scheme.startswith("postgres"):
        return uri
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if any(k.lower() == "sslmode" for k, _ in pairs):
        return uri
    sslmode = os.environ.get("DATABASE_SSLMODE", "").strip()
    if not sslmode and (parsed.hostname or "") not in LOCAL_DB_HOSTS:
        sslmode = "require"
    if sslmode:
        pairs.append(("sslmode", sslmode))
    return urlunparse(parsed._replace(query=urlencode(pairs)))


def resolve_sqlalchemy_database_uri():
    raw = os.environ.get("DATABASE_URL", "").strip()
    if raw:
        return normalize_database_url(raw)
    if os.environ.get("FLASK_ENV") == "development":
        return _dev_sqlite_uri()
    return ""


def _flag(name):
    return os.environ.get(name, "").strip() == "1"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key-change-me"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    JSON_SORT_KEYS = False

    MQTT_BROKER_URL = os.environ.get("MQTT_BROKER_URL", "mqtt://localhost:1883")
    ENABLE_MQTT = _flag("ENABLE_MQTT")

    # Demo mode runs simulated sensors inside the web process, for hosts with no MQTT broker.
    DEMO_MODE = _flag("DEMO_MODE")
    DEMO_INTERVAL_SECONDS = float(os.environ.get("DEMO_INTERVAL_SECONDS", "15"))
    RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "7"))

    # Retries for transient database errors, with exponential backoff.
    INGEST_MAX_RETRIES = int(os.environ.get("INGEST_MAX_RETRIES", "3"))
    INGEST_RETRY_BASE_DELAY = float(os.environ.get("INGEST_RETRY_BASE_DELAY", "0.5"))

    # Token for write endpoints (HTTP ingest, dead-letter replay). Unset = endpoints disabled.
    INGEST_TOKEN = os.environ.get("INGEST_TOKEN", "").strip()


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
