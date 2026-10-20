# gunicorn.conf.py
import os
import sys

# Ensure the current working directory is on the Python path
# so Gunicorn can find app.py in the repo root.
sys.path.insert(0, os.path.dirname(__file__))

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"