# tests/conftest.py
"""Pytest fixtures: app với SQLite file tạm + test client."""
import os
import tempfile

import pytest

from app import create_app
from extensions import db


@pytest.fixture
def app():
    """Tạo app test với DB file tạm, xoá sau khi xong."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    test_config = type("TestConfig", (), {
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        # Giữ nguyên các key API từ config.py (chỉ thay DB)
        "OMDB_API_KEY": "",
        "TMDB_API_KEY": "",
        "TMDB_WATCH_REGION": "US",
    })
    application = create_app(test_config)
    try:
        with application.app_context():
            yield application
    finally:
        os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _no_poster_network(monkeypatch):
    """Tránh tải poster qua mạng trong test: cache_poster chỉ passthrough URL."""
    from services import poster_cache
    monkeypatch.setattr(poster_cache, "cache_poster", lambda url, key: url or "")
