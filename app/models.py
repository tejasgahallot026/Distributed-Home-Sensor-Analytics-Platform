from datetime import datetime, timezone

from app import db


def utcnow():
    """Naive UTC timestamp, matching the existing DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SensorReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), nullable=False, index=True)
    sensor_type = db.Column(db.String(20), nullable=False)  # temperature, humidity, motion
    value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(10), default="")
    timestamp = db.Column(db.DateTime, default=utcnow, index=True)
    location = db.Column(db.String(100))

    __table_args__ = (db.Index("idx_device_time", "device_id", "timestamp"),)


class DeviceStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100))
    location = db.Column(db.String(100))
    last_seen = db.Column(db.DateTime, default=utcnow)
    status = db.Column(db.String(20), default="online")
    battery_level = db.Column(db.Float)


class DeadLetter(db.Model):
    """Messages that could not be stored, kept for inspection and replay."""

    __tablename__ = "dead_letters"

    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(200), nullable=False)
    payload = db.Column(db.Text)
    error = db.Column(db.Text)
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)  # pending | replayed
    created_at = db.Column(db.DateTime, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "topic": self.topic,
            "payload": self.payload,
            "error": self.error,
            "retry_count": self.retry_count,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
