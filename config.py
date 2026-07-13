# config.py
"""Cấu hình ứng dụng, đọc từ biến môi trường (hoặc file .env qua python-dotenv)."""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# ---- Wikidata: nguồn cấu trúc chính (không cần key, dữ liệu mở) ----
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKI_LANG = os.environ.get("WIKI_LANG", "vi")  # ngôn ngữ nhãn/tìm kiếm ưu tiên

# ---- Wikipedia REST: nội dung tóm tắt + ảnh poster ----
WIKIPEDIA_REST = "https://{lang}.wikipedia.org/api/rest_v1"
WIKIPEDIA_API = "https://{lang}.wikipedia.org/w/api.php"  # dùng để tra tiêu đề → QID

# ---- Link xem phim: ghép URL tìm kiếm JustWatch theo vùng ----
WATCH_REGION = os.environ.get("WATCH_REGION", "vn")  # mã locale JustWatch (vd: vn, us)

# Wikidata/Wikipedia yêu cầu User-Agent mô tả rõ ràng
USER_AGENT = os.environ.get(
    "USER_AGENT", "PhimAnhApp/1.0 (personal movie collection; Python-requests)"
)

# ---- Poster backend: local (mặc định) | r2 (Cloudflare R2) | remote (giữ URL gốc) ----
POSTER_BACKEND = os.environ.get("POSTER_BACKEND", "local")
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY", "")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "")
R2_PUBLIC_BASE = os.environ.get("R2_PUBLIC_BASE", "")  # vd https://pub-xxx.r2.dev

# ---- Online read-only: true → ẩn form cào (chỉ chạy local) ----
READ_ONLY = os.environ.get("READ_ONLY", "").lower() in ("1", "true", "yes")


def _build_database_uri():
    """Lấy DB URI theo thứ tự ưu tiên: DATABASE_URL → POSTGRES_PRISMA_URL (pooled) →
    POSTGRES_URL → SQLite local. Chuẩn hoá postgres:// → postgresql+psycopg2://."""
    for var in ("DATABASE_URL", "POSTGRES_PRISMA_URL", "POSTGRES_URL"):
        uri = os.environ.get(var, "").strip()
        if uri:
            break
    else:
        uri = "sqlite:///" + os.path.join(BASE_DIR, "movies.db")
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://"):]
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://"):]
    return uri


SQLALCHEMY_DATABASE_URI = _build_database_uri()
# Engine options theo loại DB (check_same_thread chỉ hợp lệ cho SQLite)
if SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False}, "pool_pre_ping": True}
else:
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}


class Config:
    """Cấu hình cho Flask + SQLAlchemy (dùng với app.config.from_object)."""
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "changeme123")
    SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = SQLALCHEMY_ENGINE_OPTIONS

