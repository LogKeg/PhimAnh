# scripts/upload_posters_to_r2.py
"""Upload ảnh poster đang cache local (static/posters/) lên Cloudflare R2,
cập nhật poster_url trong DB (Postgres qua DATABASE_URL) thành URL R2.

Chạy local sau khi set:
    DATABASE_URL=...  R2_ACCOUNT_ID=... R2_ACCESS_KEY=... R2_SECRET_KEY=...
    R2_BUCKET=phim-posters R2_PUBLIC_BASE=https://pub-xxx.r2.dev \
    python3 scripts/upload_posters_to_r2.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Phải load .env TRƯỚC khi import services/config — poster_cache import config,
# config._build_database_uri() chạy lúc import → thiếu DATABASE_URL → fallback SQLite.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from extensions import db  # noqa: E402
from models import Movie  # noqa: E402
from services.poster_cache import POSTER_DIR, R2_PUBLIC_BASE, _ext, _safe  # noqa: E402
from app import create_app  # noqa: E402


def main():
    try:
        import boto3  # noqa: F401
    except ImportError:
        sys.exit("Cài boto3: pip install -r requirements-local.txt")

    account = os.environ["R2_ACCOUNT_ID"]; bucket = os.environ["R2_BUCKET"]
    ak = os.environ["R2_ACCESS_KEY"]; sk = os.environ["R2_SECRET_KEY"]
    base = (os.environ.get("R2_PUBLIC_BASE") or "").rstrip("/")

    import boto3
    s3 = boto3.client("s3", endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
                      aws_access_key_id=ak, aws_secret_access_key=sk)

    app = create_app()
    with app.app_context():
        movies = Movie.query.filter(Movie.poster_url.like("/static/posters/%")).all()
        print(f"{len(movies)} poster local cần upload.")
        done = 0
        for m in movies:
            fname = m.poster_url.rsplit("/", 1)[-1]
            path = os.path.join(POSTER_DIR, fname)
            if not os.path.exists(path):
                continue
            ctype = "image/jpeg" if fname.lower().endswith((".jpg", ".jpeg")) else "image/png"
            s3.upload_file(path, bucket, fname, ExtraArgs={"ContentType": ctype})
            m.poster_url = f"{base}/{fname}" if base else m.poster_url
            done += 1
            if done % 50 == 0:
                db.session.commit()
                print(f"  ...{done}/{len(movies)}", flush=True)
        db.session.commit()
        print(f"Hoàn tất: upload + cập nhật {done}/{len(movies)} poster.")


if __name__ == "__main__":
    main()
