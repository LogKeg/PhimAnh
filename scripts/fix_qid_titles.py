# scripts/fix_qid_titles.py
"""Sửa phim bị lưu title = mã QID (Wikidata không có nhãn vi/en).

Phân loại:
- Không imdb_id → xoá luôn (mục rác, không rescue được).
- Có imdb_id → cào og:title từ IMDb (Playwright), cập nhật title.
  Fetch fail / vẫn rỗng → xoá luôn (không để QID sót lại).

2 pha (như scrape_posters): fetch IMDb vào RAM, ghi Postgres qua connection ngắn.

    python3 scripts/fix_qid_titles.py
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env TRƯỚC khi import app/config (tránh fallback SQLite).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from sqlalchemy import create_engine, text  # noqa: E402

from app import create_app          # noqa: E402
from extensions import db           # noqa: E402
from models import Movie            # noqa: E402
from services import imdb           # noqa: E402

QID_RE = re.compile(r"^Q\d+")
BATCH = 100          # số phim fetch chung 1 browser


def _fetch_chunk(chunk):
    """Generator: yield (movie_id, title) cho chunk qua 1 browser."""
    items = [(mid, imdb_id) for mid, imdb_id in chunk]
    for movie_id, title, _err in imdb.imdb_titles_iter(items, limit=len(items)):
        yield movie_id, title


def main():
    app = create_app()
    # Lấy danh sách phim title=QID (chỉ id + imdb_id)
    with app.app_context():
        rows = (
            db.session.query(Movie.id, Movie.imdb_id)
            .filter(Movie.title.op("~")(r"^Q\d+"))
            .order_by(Movie.id)
            .all()
        )
    junk = [(mid, im) for mid, im in rows if not im]
    rescue = [(mid, im) for mid, im in rows if im]
    print(f"{len(rows)} phim title=QID: {len(rescue)} có imdb_id (rescue), {len(junk)} rác (xoá).",
          flush=True)
    if not rows:
        print("Không có gì để sửa.")
        return

    # Pha fetch IMDb cho nhóm rescue → thu {movie_id: title} vào RAM
    titles = {}
    for i in range(0, len(rescue), BATCH):
        chunk = rescue[i:i + BATCH]
        for movie_id, title in _fetch_chunk(chunk):
            if title and not QID_RE.match(title):
                titles[movie_id] = title
        print(f"  fetch lô {i // BATCH + 1}: {len(titles)} title hợp lệ (tích lũy)", flush=True)

    # Pha ghi: xoá rác + xoá rescue-fail + update rescue-ok (connection ngắn)
    eng = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    t0 = time.time()
    with eng.begin() as conn:
        # 1. xoá phim không imdb_id (rác)
        del_junk = conn.execute(text(
            "DELETE FROM movies WHERE title ~ '^Q[0-9]+' AND (imdb_id IS NULL OR imdb_id = '')"
        )).rowcount
        # 2. xoá rescue fail (vẫn còn QID sau khi cố fetch — không sót QID lại)
        del_fail = conn.execute(text(
            "DELETE FROM movies WHERE title ~ '^Q[0-9]+' AND (imdb_id IS NOT NULL AND imdb_id <> '')"
        )).rowcount
        # 3. update rescue thành công
        updated = 0
        for movie_id, title in titles.items():
            res = conn.execute(text("UPDATE movies SET title = :t WHERE id = :i AND title ~ '^Q[0-9]+'"),
                               {"t": title, "i": movie_id})
            updated += res.rowcount

    print(f"Hoàn tất trong {time.time() - t0:.1f}s:")
    print(f"  rescue OK: {updated} (cập nhật title từ IMDb)")
    print(f"  xoá rác (không imdb_id): {del_junk}")
    print(f"  xoá rescue-fail (IMDb không có og:title): {del_fail}")
    # kiểm tra dư
    with eng.connect() as c:
        left = c.execute(text("SELECT count(*) FROM movies WHERE title ~ '^Q[0-9]+'")).scalar()
    print(f"  còn lại title=QID: {left}")


if __name__ == "__main__":
    main()
