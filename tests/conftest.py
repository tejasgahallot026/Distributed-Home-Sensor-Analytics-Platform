import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

for var in ("DATABASE_URL", "ENABLE_MQTT", "DEMO_MODE", "INGEST_TOKEN"):
    os.environ.pop(var, None)

from app import create_app, db  # noqa: E402
from app import ingest  # noqa: E402

TOKEN = "test-token"


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "test.sqlite"),
        "ENABLE_MQTT": False,
        "DEMO_MODE": False,
        "INGEST_RETRY_BASE_DELAY": 0,
        "INGEST_MAX_RETRIES": 3,
        "INGEST_TOKEN": TOKEN,
    })
    ingest.reset_metrics()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
