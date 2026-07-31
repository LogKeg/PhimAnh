# scripts/recover_qid_movies.py
"""Khôi phục 96 phim title=QID (có imdb_id) bị xoá nhầm từ fix_qid_titles cũ.

Nguồn: movies.db (snapshot SQLite Jul 13) — bản backup đủ 96 imdb_id đều thiếu
ở Postgres hiện tại. Đọc full fields → bulk insert vào Postgres (giữ title=QID
tạm). Sau đó chạy fix_qid_titles.py (đã fix UPDATE-trước) để rescue title IMDb.

    python3 scripts/recover_qid_movies.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env TRƯỚC import app — ORM target phải là Postgres (Neon), KHÔNG phải SQLite.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app import create_app          # noqa: E402
from extensions import db           # noqa: E402
from models import Movie            # noqa: E402
from sqlalchemy import text         # noqa: E402

# Cột movies.db → field Movie (bỏ imdb_rating/votes: snapshot Jul 13 chưa có,
# sẽ re-import bằng import_imdb_ratings sau)
COLS = ("wikidata_id", "imdb_id", "title", "year", "released", "genre", "director",
        "actors", "country", "language", "runtime", "plot", "poster_url",
        "wiki_title", "imdb_url", "watch_link")


def main():
    src = sqlite3.connect("movies.db")
    rows = list(src.execute(
        f'SELECT {", ".join(COLS)} FROM movies '
        'WHERE title GLOB "Q[0-9]*" AND imdb_id IS NOT NULL AND imdb_id <> ""'
    ))
    src.close()
    print(f"movies.db: {len(rows)} phim QID có imdb_id — kiểm tra trùng Postgres…", flush=True)

    app = create_app()
    with app.app_context():
        # Bỏ những imdb_id đã có (tránh trùng)
        existing = {r[0] for r in db.session.execute(
            text("SELECT imdb_id FROM movies WHERE imdb_id = ANY(:ids)"),
            {"ids": [r[1] for r in rows]},
        )}
        fresh = [r for r in rows if r[1] not in existing]
        print(f"  đã có: {len(rows) - len(fresh)}, cần insert: {len(fresh)}", flush=True)
        if not fresh:
            print("Không có gì để khôi phục.")
            return
        mappings = [dict(zip(COLS, r)) for r in fresh]
        db.session.bulk_insert_mappings(Movie, mappings)
        db.session.commit()
        print(f"Đã khôi phục {len(fresh)} phim (title=QID tạm). "
              f"Chạy fix_qid_titles.py để lấy tên IMDb, rồi import_imdb_ratings.py.")


if __name__ == "__main__":
    main()
