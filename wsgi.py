#!/usr/bin/env python3
import os
import sys

# Add project root to Python path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from app import create_app
    application = create_app()
    print("🚀 Flask app created successfully!")
except Exception as e:
    print(f"❌ App creation failed: {e}")
    raise

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    application.run(host='0.0.0.0', port=port)
