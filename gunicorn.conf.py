# Loaded automatically by gunicorn. Must stay at one worker: the MQTT
# subscriber and demo thread run inside the web process.
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = 1
threads = 4
timeout = 120
