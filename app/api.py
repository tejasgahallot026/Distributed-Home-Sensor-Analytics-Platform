from flask import Blueprint, jsonify, request
from app import db
from app.models import SensorReading, DeviceStatus
from sqlalchemy import func, desc
from datetime import datetime, timedelta

api_bp = Blueprint('api', __name__)

@api_bp.route('/sensors/<device_id>', methods=['GET'])
def get_sensor_data(device_id):
    time_window = request.args.get('window', '1h')
    if time_window == '1h':
        window = datetime.utcnow() - timedelta(hours=1)
    elif time_window == '24h':
        window = datetime.utcnow() - timedelta(days=1)
    else:
        window = datetime.utcnow() - timedelta(hours=24)
    
    readings = db.session.query(
        SensorReading.sensor_type,
        func.avg(SensorReading.value).label('avg_value'),
        func.max(SensorReading.value).label('max_value'),
        func.min(SensorReading.value).label('min_value'),
        func.count().label('count')
    ).filter(
        SensorReading.device_id == device_id,
        SensorReading.timestamp >= window
    ).group_by(SensorReading.sensor_type).all()
    
    return jsonify([{
        'sensor_type': r.sensor_type,
        'avg_value': float(r.avg_value),
        'max_value': float(r.max_value),
        'min_value': float(r.min_value),
        'count': r.count
    } for r in readings])

@api_bp.route('/devices', methods=['GET'])
def get_devices():
    devices = DeviceStatus.query.all()
    return jsonify([{
        'device_id': d.device_id,
        'name': d.name,
        'location': d.location,
        'status': d.status,
        'last_seen': d.last_seen.isoformat(),
        'battery_level': d.battery_level
    } for d in devices])

@api_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})
