#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import json
import time
import random
import threading
from datetime import datetime

class SensorSimulator:
    def __init__(self, broker_host="mosquitto", broker_port=1883):
        self.client = mqtt.Client()
        self.client.connect(broker_host, broker_port, 60)
        self.devices = [
            {"id": "living-room-thermo", "location": "Living Room", "sensors": ["temperature", "humidity"]},
            {"id": "kitchen-motion", "location": "Kitchen", "sensors": ["motion"]},
            {"id": "bedroom-thermo", "location": "Bedroom", "sensors": ["temperature", "humidity"]}
        ]
    
    def simulate_sensor(self, device_id, sensor_type, location):
        while True:
            if sensor_type == "temperature":
                value = round(random.uniform(18, 28), 2)
                unit = "°C"
            elif sensor_type == "humidity":
                value = round(random.uniform(30, 70), 2)
                unit = "%"
            elif sensor_type == "motion":
                value = random.choice([0, 1])
                unit = ""
            
            payload = {
                "type": sensor_type,
                "value": value,
                "unit": unit,
                "location": location,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            topic = f"home/sensors/{device_id}/data"
            self.client.publish(topic, json.dumps(payload))
            print(f"Published {sensor_type}: {value} {unit} to {topic}")
            time.sleep(random.uniform(5, 30))
    
    def run(self):
        self.client.loop_start()
        for device in self.devices:
            for sensor in device["sensors"]:
                t = threading.Thread(target=self.simulate_sensor, 
                                   args=(device["id"], sensor, device["location"]))
                t.daemon = True
                t.start()
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.client.loop_stop()

if __name__ == "__main__":
    simulator = SensorSimulator()
    simulator.run()
