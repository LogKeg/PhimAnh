# app.py
"""Entry point: tạo Flask app, khởi tạo DB, tự động ALTER thêm cột mới cho DB cũ."""
import os

from flask import Flask
from sqlalchemy import inspect, text

from config import Config
from extensions import db
from models import Movie


def create_app(config_class=Config):
    """Application factory."""
    # python-dotenv tuỳ chọn: nạp biến từ file .env nếu có
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    app = Flask(__name__)
    app.config.from_object(config_class)
    db.init_app(app)

    from routes import bp
    app.register_blueprint(bp)

    with app.app_context():
        _enable_wal()
        db.create_all()
        _ensure_columns()

    return app


def _enable_wal():
    """Bật WAL + busy_timeout (chỉ SQLite) để background thread ghi mà request đọc không bị khoá."""
    from sqlalchemy import event

    if db.engine.dialect.name != "sqlite":
        return  # PostgreSQL không dùng PRAGMA
    @event.listens_for(db.engine, "connect")
    def _on_connect(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


def _ensure_columns():
    """Migration nhẹ: ALTER TABLE ADD COLUMN cho cột mới khi nâng cấp DB cũ."""
    inspector = inspect(db.engine)
    if "movies" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("movies")}
    dialect = db.engine.dialect
    for name, column in Movie.__table__.columns.items():
        if name in existing:
            continue
        col_type = column.type.compile(dialect)
        db.session.execute(text(f'ALTER TABLE movies ADD COLUMN "{name}" {col_type}'))
    db.session.commit()


app = create_app()

if __name__ == "__main__":
    # use_reloader=False: reloader fork lại create_app → kẹt connection khi dùng Postgres
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True, use_reloader=False)
