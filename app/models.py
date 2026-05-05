from app import db
from datetime import datetime
from sqlalchemy import func

class SensorReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), nullable=False, index=True)
    sensor_type = db.Column(db.String(20), nullable=False)  # temp, humidity, motion
    value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(10), default='')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    location = db.Column(db.String(100))
    
    __table_args__ = (db.Index('idx_device_time', 'device_id', 'timestamp'),)

class DeviceStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100))
    location = db.Column(db.String(100))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='online')
    battery_level = db.Column(db.Float)

class DeadLetterQueue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text)
    error = db.Column(db.Text)
    retry_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
