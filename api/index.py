# api/index.py
"""Entry cho Vercel serverless: export Flask app. Vercel chạy file này cho mọi route."""
import os
import sys

# Đảm bảo import được các module ở thư mục gốc
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402,F401  (Vercel cần biến `app`)
