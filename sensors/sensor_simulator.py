#!/usr/bin/env python3
"""Publishes simulated readings to MQTT, as real home sensors would.

Configure with MQTT_BROKER_URL (default mqtt://localhost:1883) and
SIM_INTERVAL_SECONDS (default 5). Retries the broker connection until it is up.
"""
import json
import os
import random
import threading
import time
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

DEVICES = [
    {"id": "living-room", "name": "Living room thermostat", "location": "Living room", "sensors": ["temperature", "humidity"]},
    {"id": "kitchen", "name": "Kitchen hub", "location": "Kitchen", "sensors": ["temperature", "motion"]},
    {"id": "bedroom", "name": "Bedroom sensor", "location": "Bedroom", "sensors": ["temperature", "humidity"]},
]
UNITS = {"temperature": "°C", "humidity": "%", "motion": ""}


def connect(url):
    parsed = urlparse(url)
    client = mqtt.Client(client_id=f"sensor-sim-{os.getpid()}")
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    while True:
        try:
            client.connect(parsed.hostname or "localhost", parsed.port or 1883, keepalive=60)
            print(f"Connected to MQTT broker at {parsed.hostname}:{parsed.port or 1883}", flush=True)
            return client
        except OSError as exc:
            print(f"Broker not reachable ({exc}); retrying in 3s", flush=True)
            time.sleep(3)


def simulate(client, device, sensor, interval, stop):
    value = {"temperature": 21.0, "humidity": 45.0}.get(sensor, 0)
    topic = f"home/sensors/{device['id']}/data"
    while not stop.is_set():
        if sensor == "motion":
            value = 1 if random.random() < 0.3 else 0
        elif sensor == "temperature":
            value = round(min(28, max(16, value + random.uniform(-0.3, 0.3))), 2)
        else:
            value = round(min(70, max(30, value + random.uniform(-1.5, 1.5))), 2)
        payload = {"type": sensor, "value": value, "unit": UNITS[sensor], "location": device["location"]}
        client.publish(topic, json.dumps(payload), qos=1)
        print(f"{topic} {sensor}={value}", flush=True)
        stop.wait(interval * random.uniform(0.7, 1.3))


def heartbeat(client, interval, stop):
    battery = {d["id"]: random.uniform(70, 100) for d in DEVICES}
    while not stop.is_set():
        for device in DEVICES:
            battery[device["id"]] = max(5.0, battery[device["id"]] - random.uniform(0, 0.1))
            status = {"name": device["name"], "location": device["location"], "status": "online",
                      "battery": round(battery[device["id"]], 1)}
            client.publish(f"home/devices/{device['id']}/status", json.dumps(status), qos=1)
        stop.wait(interval * 6)


def main():
    interval = float(os.environ.get("SIM_INTERVAL_SECONDS", "5"))
    client = connect(os.environ.get("MQTT_BROKER_URL", "mqtt://localhost:1883"))
    client.loop_start()
    stop = threading.Event()
    threads = [threading.Thread(target=heartbeat, args=(client, interval, stop), daemon=True)]
    for device in DEVICES:
        for sensor in device["sensors"]:
            threads.append(threading.Thread(target=simulate, args=(client, device, sensor, interval, stop), daemon=True))
    for t in threads:
        t.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
        client.loop_stop()


if __name__ == "__main__":
    main()
