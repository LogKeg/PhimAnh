# extensions.py
"""Khởi tạo Flask-SQLAlchemy tách rời để tránh phụ thuộc vòng khi import."""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
