# scripts/upload_posters_to_cloudinary.py
"""Upload ảnh poster đang cache local (static/posters/) lên Cloudinary,
cập nhật poster_url trong DB thành URL Cloudinary.

Chạy local sau khi set:
    DATABASE_URL=...  CLOUDINARY_CLOUD_NAME=... CLOUDINARY_API_KEY=... CLOUDINARY_API_SECRET=... \
    python3 scripts/upload_posters_to_cloudinary.py
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
from services.poster_cache import POSTER_DIR  # noqa: E402
from app import create_app  # noqa: E402


def main():
    try:
        import cloudinary  # noqa: F401
    except ImportError:
        sys.exit("Cài cloudinary: pip install -r requirements-local.txt")

    import cloudinary
    from cloudinary import uploader
    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        secure=True,
    )

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
            public_id = os.path.splitext(fname)[0]
            res = uploader.upload(path, public_id=public_id, unique_filename=False,
                                  overwrite=True, resource_type="image")
            m.poster_url = res.get("secure_url") or m.poster_url
            done += 1
            if done % 25 == 0:
                db.session.commit()
                print(f"  ...{done}/{len(movies)}", flush=True)
        db.session.commit()
        print(f"Hoàn tất: upload + cập nhật {done}/{len(movies)} poster.")


if __name__ == "__main__":
    main()
