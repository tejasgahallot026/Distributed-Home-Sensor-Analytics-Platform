import logging
import os
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

from app.ingest import handle_message

log = logging.getLogger(__name__)

TOPICS = [("home/sensors/+/data", 1), ("home/devices/+/status", 1)]


class MQTTHandler:
    """Subscribes to sensor topics and hands every message to the ingest pipeline.

    paho's network loop reconnects automatically (1 s to 30 s backoff), and the
    subscriptions are renewed in on_connect after every reconnect.
    """

    def __init__(self, app, broker_url):
        self.app = app
        parsed = urlparse(broker_url)
        self.host = parsed.hostname or "localhost"
        self.port = parsed.port or 1883
        self.connected = False
        self.client = mqtt.Client(client_id=f"sensor-platform-{os.getpid()}", clean_session=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

    def start(self):
        log.info("Connecting to MQTT broker at %s:%s", self.host, self.port)
        self.client.connect_async(self.host, self.port, keepalive=60)
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            client.subscribe(TOPICS)
            log.info("MQTT connected; subscribed to %s", [t for t, _ in TOPICS])
        else:
            log.error("MQTT connection refused (code %s)", rc)

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc != 0:
            log.warning("MQTT connection lost (code %s); reconnecting", rc)

    def _on_message(self, client, userdata, msg):
        handle_message(self.app, msg.topic, msg.payload)
