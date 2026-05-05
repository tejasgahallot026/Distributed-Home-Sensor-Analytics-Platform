#!/usr/bin/env python3
"""
WSGI config for Render deployment.
"""
import os
from app import create_app

# Create Flask application
application = create_app()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    application.run(host='0.0.0.0', port=port)
