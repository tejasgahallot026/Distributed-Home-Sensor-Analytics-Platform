import hmac
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func, text

from app import db
from app.ingest import handle_message, metrics_snapshot, replay
from app.models import DeadLetter, DeviceStatus, SensorReading, utcnow

api_bp = Blueprint("api", __name__)

WINDOWS = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}
ONLINE_AFTER = timedelta(minutes=5)


def _since():
    hours = WINDOWS.get(request.args.get("window", "24h"), 24)
    return utcnow() - timedelta(hours=hours)


def _iso(dt):
    return dt.isoformat() + "Z" if dt else None


def _authorised():
    expected = current_app.config.get("INGEST_TOKEN", "")
    supplied = request.headers.get("X-Ingest-Token", "")
    return bool(expected) and hmac.compare_digest(expected, supplied)


def _token_error():
    if not current_app.config.get("INGEST_TOKEN"):
        return jsonify(error="Write endpoints are disabled. Set INGEST_TOKEN to enable them."), 403
    return jsonify(error="Missing or invalid X-Ingest-Token header."), 401


@api_bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db.session.rollback()
        db_ok = False
    mqtt = current_app.extensions.get("mqtt")
    body = {
        "status": "healthy" if db_ok else "degraded",
        "database": "ok" if db_ok else "unreachable",
        "mqtt": "disabled" if mqtt is None else ("connected" if mqtt.connected else "disconnected"),
        "demo_mode": bool(current_app.config.get("DEMO_MODE")),
        "timestamp": _iso(utcnow()),
    }
    return jsonify(body), 200 if db_ok else 503


@api_bp.get("/stats")
def stats():
    now = utcnow()
    last = db.session.query(func.max(SensorReading.timestamp)).scalar()
    devices = DeviceStatus.query.all()
    return jsonify(
        readings_total=SensorReading.query.count(),
        readings_last_hour=SensorReading.query.filter(SensorReading.timestamp >= now - timedelta(hours=1)).count(),
        last_reading_at=_iso(last),
        devices_total=len(devices),
        devices_online=sum(1 for d in devices if d.last_seen and now - d.last_seen <= ONLINE_AFTER),
        dead_letters_pending=DeadLetter.query.filter_by(status="pending").count(),
        since_start=metrics_snapshot(),
    )


@api_bp.get("/devices")
def devices():
    now = utcnow()
    rows = DeviceStatus.query.order_by(DeviceStatus.device_id).all()
    return jsonify([
        {
            "device_id": d.device_id,
            "name": d.name,
            "location": d.location,
            "status": d.status if d.last_seen and now - d.last_seen <= ONLINE_AFTER else "offline",
            "last_seen": _iso(d.last_seen),
            "battery_level": d.battery_level,
        }
        for d in rows
    ])


@api_bp.get("/readings")
def readings():
    query = SensorReading.query.filter(SensorReading.timestamp >= _since())
    if request.args.get("device_id"):
        query = query.filter(SensorReading.device_id == request.args["device_id"])
    if request.args.get("sensor_type"):
        query = query.filter(SensorReading.sensor_type == request.args["sensor_type"])
    limit = min(max(request.args.get("limit", 500, type=int), 1), 5000)
    rows = query.order_by(SensorReading.timestamp.desc()).limit(limit).all()
    return jsonify([
        {"device_id": r.device_id, "sensor_type": r.sensor_type, "value": r.value,
         "unit": r.unit, "location": r.location, "timestamp": _iso(r.timestamp)}
        for r in reversed(rows)
    ])


@api_bp.get("/chart-data")
def chart_data():
    """Time series for one sensor type, grouped by device."""
    sensor_type = request.args.get("sensor_type", "temperature")
    rows = (SensorReading.query
            .filter(SensorReading.sensor_type == sensor_type, SensorReading.timestamp >= _since())
            .order_by(SensorReading.timestamp).limit(5000).all())
    series = {}
    for r in rows:
        series.setdefault(r.device_id, []).append({"t": _iso(r.timestamp), "v": r.value})
    return jsonify(sensor_type=sensor_type, series=series)


@api_bp.get("/sensors/<device_id>")
def sensor_summary(device_id):
    rows = (db.session.query(
                SensorReading.sensor_type,
                func.avg(SensorReading.value), func.min(SensorReading.value),
                func.max(SensorReading.value), func.count())
            .filter(SensorReading.device_id == device_id, SensorReading.timestamp >= _since())
            .group_by(SensorReading.sensor_type).all())
    return jsonify([
        {"sensor_type": t, "avg_value": round(float(avg), 2), "min_value": float(lo),
         "max_value": float(hi), "count": n}
        for t, avg, lo, hi, n in rows
    ])


@api_bp.get("/dead-letters")
def dead_letters():
    query = DeadLetter.query
    if request.args.get("status"):
        query = query.filter_by(status=request.args["status"])
    limit = min(max(request.args.get("limit", 50, type=int), 1), 500)
    return jsonify([d.to_dict() for d in query.order_by(DeadLetter.created_at.desc()).limit(limit)])


@api_bp.post("/ingest")
def ingest():
    """HTTP alternative to MQTT: {"topic": "home/sensors/<id>/data", "payload": {...}}"""
    if not _authorised():
        return _token_error()
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or "topic" not in body or "payload" not in body:
        return jsonify(error='Send JSON like {"topic": "...", "payload": {...}}.'), 400
    raw = body["payload"] if isinstance(body["payload"], str) else jsonify(body["payload"]).get_data()
    ok, detail = handle_message(current_app._get_current_object(), body["topic"], raw)
    return (jsonify(status="stored"), 202) if ok else (jsonify(status="dead_lettered", error=detail), 422)


@api_bp.post("/dead-letters/<int:letter_id>/replay")
def replay_dead_letter(letter_id):
    if not _authorised():
        return _token_error()
    ok, detail = replay(current_app._get_current_object(), letter_id)
    if detail == "not found":
        return jsonify(error="Dead letter not found."), 404
    return (jsonify(status="replayed"), 200) if ok else (jsonify(status="failed", error=detail), 409)
