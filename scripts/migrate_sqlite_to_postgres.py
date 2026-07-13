# scripts/migrate_sqlite_to_postgres.py
"""Chuyển data từ movies.db (SQLite local) sang PostgreSQL (online).

Cách chạy (local, trước khi đặt DATABASE_URL=Postgres):
    DATABASE_URL="postgresql+psycopg2://user:pass@host/db" python3 scripts/migrate_sqlite_to_postgres.py

Schema được tạo tự động trên Postgres (db.create_all). Copy toàn bộ cột của Movie.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv  # nạp DATABASE_URL từ .env nếu có
    load_dotenv()
except ImportError:
    pass

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from config import BASE_DIR  # noqa: E402
from extensions import db  # noqa: E402
from models import Movie  # noqa: E402

BATCH = 500


def _normalize(uri):
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://"):]
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://"):]
    return uri


def main():
    dst = os.environ.get("DATABASE_URL")
    if not dst or dst.startswith("sqlite"):
        sys.exit("Cần DATABASE_URL chỉ tới PostgreSQL (chưa đặt hoặc đang là SQLite).")
    src_uri = f"sqlite:///{os.path.join(BASE_DIR, 'movies.db')}"

    src_engine = create_engine(src_uri)
    dst_engine = create_engine(_normalize(dst), pool_pre_ping=True)

    # Tạo lại schema trên Postgres (drop schema cũ nếu có để đúng kiểu Text)
    db.metadata.drop_all(dst_engine)
    db.metadata.create_all(dst_engine)
    print("Đã (tạo lại) schema trên Postgres.")

    Src = sessionmaker(bind=src_engine)
    Dst = sessionmaker(bind=dst_engine)
    src, dst_s = Src(), Dst()

    columns = [c.name for c in Movie.__table__.columns]
    total = src.query(Movie).count()
    print(f"{total} phim cần chuyển.")
    done = 0
    rows = src.query(Movie).yield_per(BATCH)
    buf = []
    for row in rows:
        data = {c: getattr(row, c) for c in columns}
        buf.append(Movie(**data))
        if len(buf) >= BATCH:
            dst_s.bulk_save_objects(buf)
            dst_s.commit()
            done += len(buf)
            buf = []
            print(f"  ...{done}/{total}", flush=True)
    if buf:
        dst_s.bulk_save_objects(buf)
        dst_s.commit()
        done += len(buf)
    print(f"Hoàn tất: chuyển {done}/{total} phim sang Postgres.")


if __name__ == "__main__":
    main()
