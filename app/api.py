from flask import Blueprint, jsonify, request
from app import db
from app.models import SensorReading, DeviceStatus
from sqlalchemy import func
from datetime import datetime, timedelta
import os
import random

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


@api_bp.route('/demo/seed', methods=['POST'])
def demo_seed():
    expected = os.environ.get('DEMO_SEED_SECRET', '').strip()
    if not expected:
        return jsonify(
            {'error': 'Demo seed is disabled. Set DEMO_SEED_SECRET in Render, redeploy, then POST again.'}
        ), 503
    supplied = (request.headers.get('X-Demo-Seed-Secret') or '').strip()
    if not supplied and request.is_json:
        supplied = (request.get_json(silent=True) or {}).get('secret', '') or ''
    if supplied != expected:
        return jsonify({'error': 'Invalid or missing secret.'}), 401

    device_id = 'demo-living-room'
    now = datetime.utcnow()
    n = 36
    base = 21.0
    rows = []
    for i in range(n):
        hours_ago = 24 * (1 - (i + 1) / n)
        ts = now - timedelta(hours=hours_ago)
        base += random.uniform(-0.35, 0.35)
        base = max(18.0, min(26.0, base))
        rows.append(
            SensorReading(
                device_id=device_id,
                sensor_type='temperature',
                value=round(base, 2),
                unit='°C',
                timestamp=ts,
                location='Demo',
            )
        )

    device = DeviceStatus.query.filter_by(device_id=device_id).first()
    if not device:
        device = DeviceStatus(
            device_id=device_id,
            name='Demo thermostat',
            location='Living room',
            last_seen=now,
            status='online',
            battery_level=87.5,
        )
        db.session.add(device)
    else:
        device.last_seen = now
        device.status = 'online'

    db.session.add_all(rows)
    db.session.commit()
    return jsonify({'ok': True, 'inserted_readings': len(rows), 'device_id': device_id})
