# Distributed Home Sensor Analytics Platform

A real-time IoT data pipeline. Simulated home sensors publish readings over **MQTT**. A **Flask** service validates each message and stores it in **PostgreSQL**, retrying transient database failures and sending anything it cannot store to a **dead-letter queue** that can be inspected and replayed. A live dashboard shows readings, device health and pipeline statistics.

## Architecture

```
 sensor simulator ──MQTT──▶ Mosquitto broker ──▶ Flask ingest service ──▶ PostgreSQL
 (3 devices, 6 sensors)        (QoS 1)            │  validate                ▲
                                                  │  retry with backoff      │
                         HTTP POST /api/ingest ──▶│  dead-letter on failure ─┘
                                                  ▼
                                   REST API + live dashboard (Chart.js)
```

Every message source (MQTT, the HTTP endpoint and the demo simulator) goes through one function, `handle_message` in [`app/ingest.py`](app/ingest.py):

1. **Validate.** The topic must be `home/sensors/<device>/data` or `home/devices/<device>/status`. The payload must be a JSON object, sensor types must be known (temperature, humidity, motion), and values must be numbers. Invalid messages go straight to the dead-letter queue, because retrying cannot fix them.
2. **Store.** Each reading is written, and the device record is upserted by `device_id`, so it shows as online.
3. **Retry.** Transient database errors (`OperationalError`, such as a dropped connection) are retried up to 3 times with exponential backoff (0.5 s, 1 s, 2 s).
4. **Dead-letter.** If the retries run out, the raw message, the error and the retry count are saved to the `dead_letters` table. `POST /api/dead-letters/<id>/replay` reprocesses a message once the problem is fixed.

The MQTT client reconnects automatically (1 to 30 s backoff) and renews its subscriptions after every reconnect.

## Run the full stack locally

Requires Docker.

```bash
cp .env.example .env        # then set POSTGRES_PASSWORD
docker compose up --build
```

Open http://localhost:5000. Within a few seconds the simulator's readings flow through Mosquitto into Postgres and appear on the dashboard. The stack has four services: `mosquitto`, `db` (Postgres 15 with a health check), `web` and `simulator`.

To see the dead-letter queue work, publish a malformed message:

```bash
docker compose exec mosquitto mosquitto_pub -t home/sensors/test/data -m '{"type": "temperature", "value": "hot"}'
```

## Cloud demo mode

Free cloud hosts such as Render do not run an MQTT broker, so the deployed demo sets `DEMO_MODE=1`. Simulated sensors then run inside the web process and send their messages through the same `handle_message` pipeline. About 1 in 40 messages is deliberately malformed, so the dead-letter queue has something to show. Readings older than 7 days are pruned. Free hosting wipes the database on restart, so the demo stores data in SQLite and, when the database is empty, backfills 6 hours of simulated history (`DEMO_BACKFILL_HOURS`). The dashboard labels this mode clearly.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Database and MQTT status (`503` if the database is unreachable) |
| GET | `/api/stats` | Totals, readings in the last hour, devices online, dead letters pending, counters since start |
| GET | `/api/devices` | Devices with status (offline after 5 minutes of silence) and battery |
| GET | `/api/readings?device_id=&sensor_type=&window=1h\|6h\|24h\|7d&limit=` | Raw readings |
| GET | `/api/chart-data?sensor_type=temperature&window=24h` | Time series grouped by device |
| GET | `/api/sensors/<device_id>?window=` | Average, minimum, maximum and count per sensor type |
| GET | `/api/dead-letters?status=pending` | Dead-letter queue |
| POST | `/api/ingest` | Ingest over HTTP: `{"topic": "...", "payload": {...}}`. Needs `X-Ingest-Token` |
| POST | `/api/dead-letters/<id>/replay` | Reprocess a dead letter. Needs `X-Ingest-Token` |

The two write endpoints are disabled unless `INGEST_TOKEN` is set.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | none | PostgreSQL URL. SSL is required automatically for remote hosts, not for `localhost` or `db`. Override with `DATABASE_SSLMODE` |
| `FLASK_ENV=development` | | Use a local SQLite file if `DATABASE_URL` is unset |
| `ENABLE_MQTT=1` | off | Subscribe to `MQTT_BROKER_URL` (default `mqtt://localhost:1883`) |
| `DEMO_MODE=1` | off | Run simulated sensors in-process (`DEMO_INTERVAL_SECONDS`, default 15) |
| `INGEST_MAX_RETRIES`, `INGEST_RETRY_BASE_DELAY` | 3, 0.5 s | Retry policy |
| `INGEST_TOKEN` | empty | Enables the write endpoints |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

The tests run against SQLite. They cover validation, device upserts, retries (simulated with injected database errors), dead-lettering, replay, every API endpoint, token protection and the SSL rules.

## Project structure

```
app/ingest.py          Validation, retries, dead-letter queue, replay
app/mqtt_handler.py    MQTT subscriber with automatic reconnects
app/demo.py            In-process simulated sensors for cloud demo mode
app/api.py             REST API
app/models.py          SensorReading, DeviceStatus, DeadLetter
templates/dashboard.html  Live dashboard
sensors/sensor_simulator.py  Standalone MQTT publisher used by Docker Compose
mosquitto/mosquitto.conf     Broker config (Mosquitto 2.x needs an explicit listener)
docker-compose.yml     Broker, Postgres, web app and simulator
tests/                 pytest suite
```

## Limitations

- The broker allows anonymous connections, which is fine for a local demo but not for real devices. Production would need TLS and per-device credentials.
- The web process runs one Gunicorn worker, because the MQTT subscriber lives inside it. Scaling out would mean moving the subscriber into its own worker service.
- Tables are created with `db.create_all()`. Schema changes would need a migration tool such as Alembic.
