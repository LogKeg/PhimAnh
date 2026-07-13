# wsgi.py
"""WSGI entry cho production server (gunicorn trên VPS): gunicorn wsgi:app"""
from app import app  # noqa: F401
