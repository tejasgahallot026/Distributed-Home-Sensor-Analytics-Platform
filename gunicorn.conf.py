# Loaded automatically by gunicorn from the project root.
# Must stay at one worker: the MQTT subscriber and demo thread run inside it.
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = 1
threads = 4
timeout = 120

# Start background threads in the worker, not the master. Some hosts (Render
# included) run gunicorn with --preload, which creates the app in the master
# process; threads started there would not exist in the worker serving requests.
os.environ["BACKGROUND_SERVICES"] = "post_fork"


def post_fork(server, worker):
    application = worker.app.wsgi()
    from app import db, start_background_services

    with application.app_context():
        db.engine.dispose(close=False)  # never reuse connections opened before the fork
    start_background_services(application)
