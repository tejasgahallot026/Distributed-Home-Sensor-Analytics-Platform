from app.demo import DEVICES, backfill
from app.models import SensorReading


def test_backfill_fills_empty_database_once(app):
    sensors = sum(len(d["sensors"]) for d in DEVICES)
    added, state = backfill(app, hours=1)
    assert added == 12 * sensors  # one reading per sensor every 5 minutes
    assert state  # live simulation continues from the last values
    with app.app_context():
        assert SensorReading.query.count() == added
    assert backfill(app, hours=1)[0] == 0  # never runs on a database that has data
