"""Simulated sensors for hosts without an MQTT broker (e.g. free cloud hosting).

Messages go through exactly the same ingest pipeline as real MQTT traffic.
About 1 in 40 messages is deliberately malformed so the dead-letter queue
can be seen working. On free hosting the database is wiped whenever the server
restarts, so an empty database is first backfilled with simulated history
(DEMO_BACKFILL_HOURS, default 6) so the charts are never blank.
"""
import json
import logging
import os
import random
import threading
import time
from datetime import timedelta

from app import db
from app.ingest import SENSOR_UNITS, handle_message
from app.models import DeadLetter, SensorReading, utcnow

log = logging.getLogger(__name__)

DEVICES = [
    {"id": "living-room", "name": "Living room thermostat", "location": "Living room",
     "sensors": ["temperature", "humidity"]},
    {"id": "kitchen", "name": "Kitchen hub", "location": "Kitchen", "sensors": ["temperature", "motion"]},
    {"id": "bedroom", "name": "Bedroom sensor", "location": "Bedroom", "sensors": ["temperature", "humidity"]},
]
START = {"temperature": 21.0, "humidity": 45.0}
BOUNDS = {"temperature": (16.0, 28.0), "humidity": (30.0, 70.0)}
STEP = {"temperature": 0.3, "humidity": 1.5}
FAULT_EVERY = 40


def start_demo(app):
    if app.extensions.get("demo_thread"):
        return
    thread = threading.Thread(target=_run, args=(app,), name="demo-sensors", daemon=True)
    app.extensions["demo_thread"] = thread
    thread.start()
    log.info("Demo mode: simulated sensors started")


def _next_value(state, key, sensor, rng):
    if sensor == "motion":
        return 1 if rng.random() < 0.3 else 0
    low, high = BOUNDS[sensor]
    value = state.get(key, START[sensor]) + rng.uniform(-STEP[sensor], STEP[sensor])
    value = min(high, max(low, value))
    state[key] = value
    return round(value, 2)


def prune(app, days):
    cutoff = utcnow() - timedelta(days=days)
    with app.app_context():
        SensorReading.query.filter(SensorReading.timestamp < cutoff).delete()
        DeadLetter.query.filter(DeadLetter.created_at < cutoff).delete()
        db.session.commit()


def backfill(app, hours, step_minutes=5):
    """Insert simulated history into an empty database. Returns (rows added, last values)."""
    state = {}
    with app.app_context():
        if hours <= 0 or SensorReading.query.first() is not None:
            return 0, state
        rng, now = random.Random(), utcnow()
        steps = int(hours * 60 / step_minutes)
        rows = []
        for i in range(steps, 0, -1):
            ts = now - timedelta(minutes=step_minutes * i)
            for device in DEVICES:
                for sensor in device["sensors"]:
                    value = _next_value(state, f"{device['id']}:{sensor}", sensor, rng)
                    rows.append(SensorReading(device_id=device["id"], sensor_type=sensor, value=value,
                                              unit=SENSOR_UNITS[sensor], location=device["location"], timestamp=ts))
        db.session.add_all(rows)
        db.session.commit()
    log.info("Demo mode: backfilled %d simulated readings covering %s hours", len(rows), hours)
    return len(rows), state


def _run(app):
    rng = random.Random()
    try:
        _, state = backfill(app, float(os.environ.get("DEMO_BACKFILL_HOURS", "6")))
    except Exception:
        log.exception("Demo backfill failed")
        state = {}
    battery = {d["id"]: rng.uniform(70, 100) for d in DEVICES}
    count, last_prune = 0, 0.0
    interval = app.config["DEMO_INTERVAL_SECONDS"]
    while True:
        try:
            for device in DEVICES:
                for sensor in device["sensors"]:
                    count += 1
                    topic = f"home/sensors/{device['id']}/data"
                    if count % FAULT_EVERY == 0:
                        handle_message(app, topic, b'{"type": "temperature", "value": ')  # truncated JSON
                        continue
                    payload = {"type": sensor, "value": _next_value(state, f"{device['id']}:{sensor}", sensor, rng),
                               "location": device["location"]}
                    handle_message(app, topic, json.dumps(payload).encode())
                battery[device["id"]] = max(5.0, battery[device["id"]] - rng.uniform(0, 0.05))
                status = {"name": device["name"], "location": device["location"], "status": "online",
                          "battery": round(battery[device["id"]], 1)}
                handle_message(app, f"home/devices/{device['id']}/status", json.dumps(status).encode())
            if time.time() - last_prune > 3600:
                prune(app, app.config["RETENTION_DAYS"])
                last_prune = time.time()
        except Exception:
            log.exception("Demo loop error")
        time.sleep(interval)
