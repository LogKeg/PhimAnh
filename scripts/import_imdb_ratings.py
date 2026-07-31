# scripts/import_imdb_ratings.py
"""Nhập điểm IMDb từ dataset chính thức (non-commercial use) vào Postgres.

Nguồn: https://datasets.imdbws.com/title.ratings.tsv.gz  (cập nhật hằng ngày)
TSV: tconst (tt...) | averageRating (0.0-10.0) | numVotes

Cài nhanh: tải 1 file ~5MB → lọc theo imdb_id đang có → bulk UPDATE qua temp table
JOIN (~11k phim trong vài giây, không cào web, không API key, không rate-limit).

    python3 scripts/import_imdb_ratings.py
"""
import csv
import gzip
import os
import ssl
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Phải load .env TRƯỚC khi đọc DATABASE_URL (config fallback SQLite nếu thiếu).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from sqlalchemy import create_engine, text  # noqa: E402

RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"


def _our_imdb_ids(conn):
    """Tập imdb_id hiện có trong DB (để lọc TSV, tránh insert 1.3M dòng vô dụng)."""
    rows = conn.execute(text(
        "SELECT DISTINCT imdb_id FROM movies WHERE imdb_id IS NOT NULL AND imdb_id <> ''"
    ))
    return {r[0] for r in rows}


def fetch_ratings(wanted):
    """Tải + giải nén TSV, chỉ giữ dòng có tconst trong `wanted`. Trả về list tuples."""
    # macOS framework Python thiếu CA gốc → dùng certifi nếu có
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = None
    req = urllib.request.Request(RATINGS_URL, headers={"User-Agent": "PhimAnhApp/1.0"})
    rows = []
    with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:        # ~5MB
        with gzip.open(resp, "rt", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                tconst = row["tconst"]
                if tconst not in wanted:
                    continue
                rating_raw, votes_raw = row["averageRating"], row["numVotes"]
                rating = float(rating_raw) if rating_raw and rating_raw != "\\N" else None
                votes = int(votes_raw) if votes_raw and votes_raw != "\\N" else None
                rows.append({"t": tconst, "r": rating, "v": votes})
    return rows


def _bulk_insert(conn, rows, chunk=500):
    """INSERT nhiều dòng vào imdb_ratings qua multi-row VALUES chunked.

    executemany mặc định gửi từng dòng (chậm qua Neon remote). Chunked VALUES
    giảm còn ~len(rows)/chunk round-trip (11k dòng → ~22 câu).
    """
    for i in range(0, len(rows), chunk):
        block = rows[i:i + chunk]
        placeholders = ",".join(f"(:t{k},:r{k},:v{k})" for k in range(len(block)))
        params = {}
        for k, row in enumerate(block):
            params[f"t{k}"], params[f"r{k}"], params[f"v{k}"] = row["t"], row["r"], row["v"]
        conn.execute(text(f"INSERT INTO imdb_ratings (tconst, rating, votes) VALUES {placeholders}"), params)


def main():
    if not os.environ.get("DATABASE_URL"):
        sys.exit("Thiếu DATABASE_URL trong env.")
    eng = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    t0 = time.time()
    with eng.connect() as conn:
        wanted = _our_imdb_ids(conn)
        total_movies = conn.execute(text("SELECT count(*) FROM movies")).scalar()
    print(f"{len(wanted)} imdb_id trong DB ({total_movies} phim) — tải dataset IMDb…", flush=True)

    rows = fetch_ratings(wanted)
    print(f"Matched {len(rows)}/{len(wanted)} title có rating — đang ghi Postgres…", flush=True)
    if not rows:
        print("Không có gì để ghi.")
        return

    with eng.begin() as conn:
        conn.execute(text("CREATE TEMP TABLE imdb_ratings (tconst TEXT, rating NUMERIC(3,1), votes INT)"))
        _bulk_insert(conn, rows)
        res = conn.execute(text("""
            UPDATE movies SET imdb_rating = r.rating, imdb_votes = r.votes
            FROM imdb_ratings r WHERE movies.imdb_id = r.tconst
        """))
        updated = res.rowcount
        # Phim có imdb_id nhưng KHÔNG có trong dataset (ít vote) → đặt NULL cho rõ
        conn.execute(text("""
            UPDATE movies SET imdb_rating = NULL, imdb_votes = NULL
            WHERE imdb_id IS NOT NULL AND imdb_id <> ''
              AND imdb_id NOT IN (SELECT tconst FROM imdb_ratings)
        """))
        have = conn.execute(text("SELECT count(*) FROM movies WHERE imdb_rating IS NOT NULL")).scalar()

    print(f"Hoàn tất trong {time.time() - t0:.1f}s: cập nhật {updated} phim, "
          f"{have}/{total_movies} phim có điểm IMDb ({round(100 * have / total_movies)}%).")


if __name__ == "__main__":
    main()
