# scripts/scrape_posters.py
"""Cào poster IMDb cho phim thiếu, upload Cloudinary, ghi Postgres.

Tách 2 pha để tránh connection Postgres bị đóng do idle timeout (fetch IMDb rất chậm):
- Pha fetch: Playwright + upload Cloudinary, chỉ thu kết quả vào RAM (không đụng DB).
- Pha ghi: cập nhật Postgres qua connection ngắn (engine.begin, pool_pre_ping).

    python3 scripts/scrape_posters.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from sqlalchemy import create_engine, text  # noqa: E402

from app import create_app          # noqa: E402
from extensions import db           # noqa: E402
from models import Movie            # noqa: E402
from services import imdb, poster_cache  # noqa: E402

BATCH = 100          # số phim fetch chung 1 browser
FLUSH = 50           # ghi DB mỗi 50 poster


def _flush(eng, updates):
    """Ghi nhanh {movie_id: url} vào Postgres qua connection ngắn. Retry chống transient."""
    if not updates:
        return
    rows = list(updates.items())
    updates.clear()
    for attempt in range(4):
        try:
            with eng.begin() as conn:
                for mid, url in rows:
                    conn.execute(text("UPDATE movies SET poster_url = :u WHERE id = :i"),
                                 {"u": url, "i": mid})
            return
        except Exception as exc:  # pylint: disable=broad-except
            if attempt < 3:
                time.sleep(3 * (attempt + 1))   # 3s, 6s, 9s rồi thử lại
                continue
            updates.update(rows)                # đặt lại để không mất, rồi báo lỗi
            print(f"  ⚠ flush thất bại sau 4 lần: {exc}", flush=True)
            raise


def main():
    app = create_app()
    # Lấy danh sách phim thiếu (chỉ id + imdb_id) — không giữ ORM object qua pha fetch
    with app.app_context():
        rows = (
            db.session.query(Movie.id, Movie.imdb_id)
            .filter((Movie.poster_url.is_(None)) | (Movie.poster_url == ""))
            .filter(Movie.imdb_id.isnot(None), Movie.imdb_id != "")
            .order_by(Movie.id)
            .all()
        )
    total = len(rows)
    print(f"{total} phim thiếu poster — fetch IMDb (~15-30s/phim), ghi DB mỗi {FLUSH}", flush=True)
    if total == 0:
        print("Không còn phim thiếu poster.")
        return

    eng = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    updates = {}
    updated = 0
    for i in range(0, total, BATCH):
        chunk = rows[i:i + BATCH]
        for movie_id, imdb_id, url, err in _fetch_chunk(chunk):
            if url:
                updates[movie_id] = poster_cache.cache_poster(url, imdb_id)
                updated += 1
                if len(updates) >= FLUSH:
                    _flush(eng, updates)
                    print(f"  lô {i // BATCH + 1}: đã ghi {updated} poster", flush=True)
        _flush(eng, updates)
        print(f"lô {i // BATCH + 1}: xong {len(chunk)} phim (tích lũy {updated}/{total})", flush=True)
    print(f"Hoàn tất: +{updated}/{total} poster.")


def _fetch_chunk(chunk):
    """Generator: yield (movie_id, imdb_id, url, err) cho chunk qua 1 browser."""
    items = [(mid, imdb_id) for mid, imdb_id in chunk]
    for movie_id, url, err in imdb.imdb_posters_iter(items, limit=len(items)):
        # tìm imdb_id tương ứng
        imdb_id = next((im for mid, im in chunk if mid == movie_id), "")
        yield movie_id, imdb_id, url, err


if __name__ == "__main__":
    main()
