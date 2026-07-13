# scripts/refresh_metadata.py
"""Backfill genre/country/actors/director/language cho phim thiếu metadata.

Mỗi phim thiếu được xử lý ĐÚNG 1 LẦN (load hết rồi chia lô), mỗi lô retry 2 lần
chống lỗi transient của Wikidata. Giữ nguyên plot/poster (partial không chứa 2 trường đó).

    python3 scripts/refresh_metadata.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app          # noqa: E402
from models import Movie            # noqa: E402
from queries import upsert_movie    # noqa: E402
from services import wikidata       # noqa: E402

BATCH = 100
RETRIES = 2


def main():
    app = create_app()
    with app.app_context():
        missing = (
            Movie.query
            .filter((Movie.genre.is_(None)) | (Movie.genre == ""))
            .filter(Movie.wikidata_id.isnot(None), Movie.wikidata_id != "")
            .all()
        )
        total = len(missing)
        print(f"{total} phim thiếu metadata — xử lý mỗi phim 1 lần", flush=True)
        updated, n_batches = 0, 0
        for i in range(0, total, BATCH):
            n_batches += 1
            chunk = missing[i:i + BATCH]
            qids = [m.wikidata_id for m in chunk]
            films, err = None, None
            for _attempt in range(RETRIES):          # chống lỗi transient Wikidata
                films, err = wikidata.films_by_qids(qids)
                if not err and films:
                    break
            if err or not films:
                print(f"lô {n_batches}: lỗi SPARQL — bỏ qua (chạy lại script để thử)", flush=True)
                continue
            by_qid = {f["wikidata_id"]: f for f in films}
            cnt = 0
            for movie in chunk:
                partial = by_qid.get(movie.wikidata_id)
                if partial and (partial.get("genre") or partial.get("actors")):
                    upsert_movie(partial)            # cập nhật metadata, giữ plot/poster
                    cnt += 1
            updated += cnt
            print(f"lô {n_batches}: {cnt}/{len(chunk)} (tích lũy {updated}/{total})", flush=True)
        print(f"Hoàn tất: +{updated}/{total} phim có metadata.")


if __name__ == "__main__":
    main()
