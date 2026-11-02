"""Message ingestion shared by MQTT, the HTTP endpoint and demo mode.

Flow: parse and validate -> store (retrying transient database errors with
exponential backoff) -> on failure, write to the dead-letter queue.
"""
import json
import logging
import threading
import time

from sqlalchemy.exc import OperationalError

from app import db
from app.models import DeadLetter, DeviceStatus, SensorReading, utcnow

log = logging.getLogger(__name__)

SENSOR_UNITS = {"temperature": "°C", "humidity": "%", "motion": ""}
DEVICE_STATES = {"online", "offline"}


class InvalidMessage(ValueError):
    """The message itself is wrong, so retrying cannot help."""


_lock = threading.Lock()
_metrics = {"received": 0, "stored": 0, "retries": 0, "dead_lettered": 0, "replayed": 0}


def _bump(key, n=1):
    with _lock:
        _metrics[key] += n


def metrics_snapshot():
    with _lock:
        return dict(_metrics)


def reset_metrics():
    with _lock:
        for key in _metrics:
            _metrics[key] = 0


def _number(value, field, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidMessage(f"Field '{field}' must be a number")
    return float(value)


def parse_message(topic, raw):
    """Validate a topic and payload, returning a normalised dict."""
    parts = (topic or "").split("/")
    if len(parts) != 4 or parts[0] != "home" or not parts[2]:
        raise InvalidMessage(f"Unsupported topic: {topic!r}")
    _, group, device_id, kind = parts
    if len(device_id) > 50:
        raise InvalidMessage("Device id is longer than 50 characters")

    try:
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
        payload = json.loads(text)
    except (UnicodeDecodeError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidMessage(f"Payload is not valid JSON: {exc}") from None
    if not isinstance(payload, dict):
        raise InvalidMessage("Payload must be a JSON object")

    if group == "sensors" and kind == "data":
        sensor_type = payload.get("type")
        if sensor_type not in SENSOR_UNITS:
            raise InvalidMessage(f"Unknown sensor type: {sensor_type!r}")
        return {
            "kind": "reading",
            "device_id": device_id,
            "sensor_type": sensor_type,
            "value": _number(payload.get("value"), "value"),
            "unit": str(payload.get("unit") or SENSOR_UNITS[sensor_type])[:10],
            "location": (str(payload["location"])[:100] if payload.get("location") else None),
        }
    if group == "devices" and kind == "status":
        state = payload.get("status", "online")
        if state not in DEVICE_STATES:
            raise InvalidMessage(f"Unknown device status: {state!r}")
        return {
            "kind": "status",
            "device_id": device_id,
            "name": (str(payload["name"])[:100] if payload.get("name") else None),
            "location": (str(payload["location"])[:100] if payload.get("location") else None),
            "status": state,
            "battery": _number(payload.get("battery"), "battery", allow_none=True),
        }
    raise InvalidMessage(f"Unsupported topic: {topic!r}")


def _apply(msg):
    """Write one validated message. Devices are upserted by device_id."""
    now = utcnow()
    device = DeviceStatus.query.filter_by(device_id=msg["device_id"]).first()
    if device is None:
        device = DeviceStatus(device_id=msg["device_id"], name=msg["device_id"])
        db.session.add(device)
    device.last_seen = now
    if msg.get("location"):
        device.location = msg["location"]

    if msg["kind"] == "reading":
        device.status = "online"
        db.session.add(
            SensorReading(
                device_id=msg["device_id"],
                sensor_type=msg["sensor_type"],
                value=msg["value"],
                unit=msg["unit"],
                location=msg.get("location") or device.location,
                timestamp=now,
            )
        )
    else:
        if msg.get("name"):
            device.name = msg["name"]
        device.status = msg["status"]
        if msg.get("battery") is not None:
            device.battery_level = msg["battery"]
    db.session.commit()


def store(app, msg):
    """Store a message, retrying transient database errors. Returns retries used."""
    max_retries = app.config["INGEST_MAX_RETRIES"]
    base_delay = app.config["INGEST_RETRY_BASE_DELAY"]
    attempt = 0
    while True:
        try:
            _apply(msg)
            return attempt
        except OperationalError as exc:
            db.session.rollback()
            if attempt >= max_retries:
                raise
            attempt += 1
            _bump("retries")
            delay = base_delay * (2 ** (attempt - 1))
            log.warning("Database error storing %s (retry %d/%d in %.1fs): %s",
                        msg["device_id"], attempt, max_retries, delay, exc.orig if hasattr(exc, "orig") else exc)
            time.sleep(delay)


def dead_letter(topic, raw, error, retries):
    _bump("dead_lettered")
    text = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    try:
        db.session.add(DeadLetter(topic=(topic or "")[:200], payload=text[:10000],
                                  error=str(error)[:2000], retry_count=retries))
        db.session.commit()
    except Exception:  # the database itself may be the problem
        db.session.rollback()
        log.exception("Could not write dead letter for topic %s", topic)
    log.warning("Dead-lettered message on %s: %s", topic, error)


def handle_message(app, topic, raw):
    """Single entry point for every message source. Never raises. Returns (ok, detail)."""
    _bump("received")
    with app.app_context():
        try:
            msg = parse_message(topic, raw)
        except InvalidMessage as exc:
            dead_letter(topic, raw, str(exc), 0)
            return False, str(exc)
        try:
            store(app, msg)
        except Exception as exc:
            db.session.rollback()
            detail = f"{type(exc).__name__}: {exc}"
            dead_letter(topic, raw, detail, app.config["INGEST_MAX_RETRIES"])
            return False, detail
        _bump("stored")
        return True, "stored"


def replay(app, letter_id):
    """Retry a dead-lettered message. Must run inside an app context."""
    letter = db.session.get(DeadLetter, letter_id)
    if letter is None:
        return False, "not found"
    if letter.status == "replayed":
        return False, "already replayed"
    try:
        msg = parse_message(letter.topic, letter.payload or "")
        store(app, msg)
    except Exception as exc:
        db.session.rollback()
        letter = db.session.get(DeadLetter, letter_id)
        letter.retry_count += 1
        letter.error = f"{type(exc).__name__}: {exc}"[:2000]
        db.session.commit()
        return False, letter.error
    letter = db.session.get(DeadLetter, letter_id)
    letter.status = "replayed"
    db.session.commit()
    _bump("replayed")
    _bump("stored")
    return True, "replayed"
