import json

from sqlalchemy.exc import OperationalError

from app import ingest
from app.ingest import handle_message, metrics_snapshot, replay
from app.models import DeadLetter, DeviceStatus, SensorReading


def reading(sensor="temperature", value=21.5, **extra):
    return json.dumps({"type": sensor, "value": value, "location": "Lab", **extra}).encode()


def test_valid_reading_is_stored_and_device_created(app):
    ok, _ = handle_message(app, "home/sensors/lab-1/data", reading())
    assert ok
    with app.app_context():
        row = SensorReading.query.one()
        assert (row.device_id, row.sensor_type, row.value, row.unit) == ("lab-1", "temperature", 21.5, "°C")
        device = DeviceStatus.query.one()
        assert device.device_id == "lab-1" and device.status == "online" and device.location == "Lab"


def test_repeated_status_updates_do_not_duplicate_device(app):
    """Regression: the old code looked devices up by primary key and crashed on the second update."""
    for battery in (90, 80):
        payload = json.dumps({"name": "Lab sensor", "status": "online", "battery": battery}).encode()
        ok, detail = handle_message(app, "home/devices/lab-1/status", payload)
        assert ok, detail
    with app.app_context():
        device = DeviceStatus.query.one()
        assert device.name == "Lab sensor" and device.battery_level == 80


def test_invalid_json_goes_to_dead_letter_queue(app):
    ok, detail = handle_message(app, "home/sensors/lab-1/data", b'{"type": "temperature", "value": ')
    assert not ok and "not valid JSON" in detail
    with app.app_context():
        letter = DeadLetter.query.one()
        assert letter.status == "pending" and letter.retry_count == 0
        assert SensorReading.query.count() == 0


def test_bad_values_and_topics_are_dead_lettered(app):
    cases = [
        ("home/sensors/lab-1/data", reading(sensor="pressure")),
        ("home/sensors/lab-1/data", reading(value="hot")),
        ("home/sensors/lab-1/data", reading(value=True)),
        ("office/sensors/lab-1/data", reading()),
        ("home/devices/lab-1/status", json.dumps({"status": "exploded"}).encode()),
    ]
    for topic, payload in cases:
        ok, _ = handle_message(app, topic, payload)
        assert not ok
    with app.app_context():
        assert DeadLetter.query.count() == len(cases)
        assert SensorReading.query.count() == 0
    assert metrics_snapshot()["dead_lettered"] == len(cases)


def test_transient_database_error_is_retried(app, monkeypatch):
    real_apply, calls = ingest._apply, {"n": 0}

    def flaky(msg):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise OperationalError("INSERT", {}, Exception("connection reset"))
        return real_apply(msg)

    monkeypatch.setattr(ingest, "_apply", flaky)
    ok, _ = handle_message(app, "home/sensors/lab-1/data", reading())
    assert ok and calls["n"] == 3
    assert metrics_snapshot()["retries"] == 2
    with app.app_context():
        assert SensorReading.query.count() == 1 and DeadLetter.query.count() == 0


def test_persistent_database_error_is_dead_lettered_then_replayed(app, monkeypatch):
    real_apply = ingest._apply

    def down(msg):
        raise OperationalError("INSERT", {}, Exception("database is down"))

    monkeypatch.setattr(ingest, "_apply", down)
    ok, detail = handle_message(app, "home/sensors/lab-1/data", reading())
    assert not ok and "database is down" in detail
    assert metrics_snapshot()["retries"] == 3

    monkeypatch.setattr(ingest, "_apply", real_apply)  # database recovers
    with app.app_context():
        letter = DeadLetter.query.one()
        assert letter.retry_count == 3
        ok, _ = replay(app, letter.id)
        assert ok
        assert DeadLetter.query.one().status == "replayed"
        assert SensorReading.query.count() == 1
        assert replay(app, letter.id) == (False, "already replayed")


def test_replay_of_malformed_message_fails_and_counts_attempt(app):
    handle_message(app, "home/sensors/lab-1/data", b"not json")
    with app.app_context():
        letter = DeadLetter.query.one()
        ok, _ = replay(app, letter.id)
        assert not ok
        assert DeadLetter.query.one().retry_count == 1
