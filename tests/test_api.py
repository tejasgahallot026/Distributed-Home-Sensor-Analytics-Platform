import json

from app.config import normalize_database_url
from app.ingest import handle_message
from conftest import TOKEN

AUTH = {"X-Ingest-Token": TOKEN}


def seed(app):
    for device, sensor, value in [("a", "temperature", 20.0), ("a", "temperature", 22.0),
                                  ("b", "temperature", 19.0), ("a", "humidity", 50.0)]:
        handle_message(app, f"home/sensors/{device}/data", json.dumps({"type": sensor, "value": value}).encode())


def test_health(client):
    body = client.get("/api/health").get_json()
    assert body["database"] == "ok" and body["mqtt"] == "disabled" and body["demo_mode"] is False


def test_dashboard_renders(client):
    assert b"Home Sensor Analytics" in client.get("/").data


def test_stats_and_devices(app, client):
    seed(app)
    handle_message(app, "home/sensors/a/data", b"broken")
    stats = client.get("/api/stats").get_json()
    assert stats["readings_total"] == 4 and stats["readings_last_hour"] == 4
    assert stats["devices_total"] == 2 and stats["devices_online"] == 2
    assert stats["dead_letters_pending"] == 1 and stats["since_start"]["stored"] == 4
    devices = client.get("/api/devices").get_json()
    assert [d["device_id"] for d in devices] == ["a", "b"] and devices[0]["status"] == "online"


def test_chart_data_groups_by_device(app, client):
    seed(app)
    body = client.get("/api/chart-data?sensor_type=temperature&window=1h").get_json()
    assert set(body["series"]) == {"a", "b"}
    assert [p["v"] for p in body["series"]["a"]] == [20.0, 22.0]


def test_readings_filters_and_summary(app, client):
    seed(app)
    rows = client.get("/api/readings?device_id=a&sensor_type=temperature").get_json()
    assert [r["value"] for r in rows] == [20.0, 22.0]
    summary = {s["sensor_type"]: s for s in client.get("/api/sensors/a").get_json()}
    assert summary["temperature"]["avg_value"] == 21.0 and summary["temperature"]["count"] == 2


def test_ingest_requires_token(client):
    body = {"topic": "home/sensors/a/data", "payload": {"type": "temperature", "value": 20}}
    assert client.post("/api/ingest", json=body).status_code == 401
    assert client.post("/api/ingest", json=body, headers={"X-Ingest-Token": "wrong"}).status_code == 401


def test_ingest_disabled_without_token(app, client):
    app.config["INGEST_TOKEN"] = ""
    body = {"topic": "home/sensors/a/data", "payload": {"type": "temperature", "value": 20}}
    assert client.post("/api/ingest", json=body).status_code == 403


def test_ingest_stores_or_dead_letters(client):
    good = {"topic": "home/sensors/a/data", "payload": {"type": "temperature", "value": 20}}
    bad = {"topic": "home/sensors/a/data", "payload": {"type": "pressure", "value": 1}}
    assert client.post("/api/ingest", json=good, headers=AUTH).status_code == 202
    resp = client.post("/api/ingest", json=bad, headers=AUTH)
    assert resp.status_code == 422 and resp.get_json()["status"] == "dead_lettered"
    letters = client.get("/api/dead-letters?status=pending").get_json()
    assert len(letters) == 1 and "pressure" in letters[0]["error"]


def test_replay_endpoint(client):
    client.post("/api/ingest", json={"topic": "home/sensors/a/data", "payload": "not json"}, headers=AUTH)
    letter_id = client.get("/api/dead-letters").get_json()[0]["id"]
    assert client.post(f"/api/dead-letters/{letter_id}/replay").status_code == 401
    assert client.post(f"/api/dead-letters/{letter_id}/replay", headers=AUTH).status_code == 409
    assert client.post("/api/dead-letters/9999/replay", headers=AUTH).status_code == 404


def test_database_url_ssl_rules(monkeypatch):
    monkeypatch.delenv("DATABASE_SSLMODE", raising=False)
    assert normalize_database_url("postgres://u:p@db:5432/s") == "postgresql://u:p@db:5432/s"
    assert normalize_database_url("postgresql://u:p@localhost/s") == "postgresql://u:p@localhost/s"
    assert normalize_database_url("postgres://u:p@x.render.com/s").endswith("?sslmode=require")
    assert normalize_database_url("postgresql://u:p@x.render.com/s?sslmode=disable").endswith("sslmode=disable")
    monkeypatch.setenv("DATABASE_SSLMODE", "disable")
    assert normalize_database_url("postgresql://u:p@x.render.com/s").endswith("sslmode=disable")
