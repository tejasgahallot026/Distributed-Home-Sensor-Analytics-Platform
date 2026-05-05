import paho.mqtt.client as mqtt
import json
from app import db
from app.models import SensorReading, DeadLetterQueue, DeviceStatus
import logging
from datetime import datetime
import time

class MQTTHandler:
    def __init__(self, broker_url="mqtt://localhost:1883"):
        self.broker_url = broker_url
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        
    def connect(self):
        try:
            self.client.connect_async("mosquitto", 1883, 60)
            self.client.loop_start()
            logging.info("MQTT client connected")
        except Exception as e:
            logging.error(f"MQTT connection failed: {e}")
    
    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logging.info("MQTT Connected successfully")
            client.subscribe("home/sensors/+/data")
            client.subscribe("home/devices/+/status")
        else:
            logging.error(f"MQTT Connection failed with code {rc}")
    
    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            self.process_message(msg.topic, payload)
        except json.JSONDecodeError as e:
            self.handle_dead_letter(msg.topic, msg.payload.decode(), str(e))
        except Exception as e:
            self.handle_dead_letter(msg.topic, msg.payload.decode(), str(e))
    
    def process_message(self, topic, payload):
        parts = topic.split('/')
        if len(parts) >= 4 and parts[0] == 'home':
            device_id = parts[2]
            
            if parts[3] == 'data':
                # Sensor data
                reading = SensorReading(
                    device_id=device_id,
                    sensor_type=payload.get('type'),
                    value=payload.get('value'),
                    unit=payload.get('unit', ''),
                    location=payload.get('location')
                )
                db.session.add(reading)
                
            elif parts[3] == 'status':
                # Device status
                status = DeviceStatus.query.get(device_id)
                if not status:
                    status = DeviceStatus(device_id=device_id)
                status.name = payload.get('name')
                status.location = payload.get('location')
                status.last_seen = datetime.utcnow()
                status.status = payload.get('status', 'online')
                status.battery_level = payload.get('battery')
                db.session.add(status)
            
            db.session.commit()
            logging.info(f"Processed message from {device_id}")
    
    def handle_dead_letter(self, topic, message, error):
        dlq_entry = DeadLetterQueue(
            message=message,
            error=error,
            retry_count=0
        )
        db.session.add(dlq_entry)
        db.session.commit()
        logging.warning(f"Message sent to DLQ: {error}")
