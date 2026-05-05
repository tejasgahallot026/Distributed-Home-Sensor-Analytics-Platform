from flask import Blueprint, render_template, jsonify
from app import db
from app.models import SensorReading, DeviceStatus
import plotly.graph_objs as go
import plotly.utils
from datetime import datetime, timedelta

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
def dashboard():
    return render_template('dashboard.html')

@dashboard_bp.route('/api/chart-data')
def chart_data():
    # Recent temperature data for visualization
    recent_data = SensorReading.query.filter(
        SensorReading.sensor_type == 'temperature',
        SensorReading.timestamp > datetime.utcnow() - timedelta(hours=24)
    ).order_by(SensorReading.timestamp).all()
    
    return jsonify([{
        'timestamp': r.timestamp.isoformat(),
        'value': r.value,
        'device_id': r.device_id
    } for r in recent_data])
