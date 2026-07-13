# Kế hoạch: Deploy Vercel (Postgres + R2) + Git

## Kiến trúc
```
Local (máy bạn, POSTER_BACKEND=r2): cào đầy đủ → PostgreSQL (Vercel Postgres) + R2 poster
Vercel (online, READ_ONLY=true):    Flask read-only → đọc Postgres → hiện R2 URL
```
Cùng 1 codebase; hành vi phân nhánh bằng env.

## Việc BẠN làm (cần tài khoản, tôi không làm thay)
1. Tạo repo **private** trên GitHub (tôi sẽ init local + push).
2. Tạo **Vercel Postgres** (dashboard Vercel → Storage → Postgres → copy `DATABASE_URL` / `POSTGRES_URL`).
3. Tạo **Cloudflare R2**: bucket (vd `phim-posters`), API token (Access Key + Secret), note account_id. Bật public domain cho bucket (vd `posters.example.com` hoặc dùng r2.dev).
4. Trên Vercel: import repo từ GitHub, set env vars: `DATABASE_URL`, `FLASK_SECRET_KEY`, `READ_ONLY=true`, `R2_*`, `POSTER_BACKEND=r2`.

## Việc TÔI code
### Pha 1 — Tương thích PostgreSQL (không phá local)
- `app.py`: WAL pragma **chỉ chạy khi SQLite** (Postgres sẽ lỗi nếu chạy PRAGMA).
- `config.py`: `SQLALCHEMY_DATABASE_URI` đọc `DATABASE_URL` (đã có) — Postgres URI hoạt động luôn.
- `_ensure_columns`: kiểm tra dialect (Postgres dùng `SERIAL`/`TEXT`...) — đã compile theo dialect, chỉ cần bỏ cú pháp SQLite-only.

### Pha 2 — Poster backend linh hoạt (env `POSTER_BACKEND`)
- `services/poster_cache.py`: thêm backend `r2` (upload S3-compatible) + `remote` (giữ URL gốc). Mặc định `local` (giữ nguyên hành vi hiện tại).
- R2 upload qua `boto3` (S3 API), lưu public URL vào `poster_url`.
- Local khi `POSTER_BACKEND=r2` → poster lên R2, DB chứa URL R2 → Vercel đọc được.

### Pha 3 — READ_ONLY mode
- `routes.py` + `index.html`: khi `READ_ONLY=true` → ẩn các form cào (collect/seed/enrich/lấy-poster/mô-tả), chỉ giữ duyệt/tìm/lọc/chi tiết. POST tới action cào → flash "chỉ dùng local".

### Pha 4 — Vercel config + Git
- `vercel.json` (Python runtime, build install requirements-vercel.txt, route `/`→Flask).
- `wsgi.py` (entry `app` cho Vercel).
- `requirements-vercel.txt`: Flask, Flask-SQLAlchemy, **psycopg2-binary**, requests, python-dotenv, boto3 — KHÔNG playwright (nặng, không chạy được trên Vercel).
- `requirements.txt`: giữ nguyên (local, có playwright).
- `.gitignore`: đã loại DB/poster/.env. Init git, commit, hướng dẫn push.

### Pha 5 — Migration data (chạy 1 lần ở local)
- `scripts/migrate_sqlite_to_postgres.py`: đọc `movies.db` SQLite → insert vào Postgres (cùng schema, SQLAlchemy create_all + bulk insert).
- `scripts/upload_posters_to_r2.py`: quét `static/posters/*.jpg` → upload R2 → update `poster_url` thành URL R2 trong Postgres.

## Thứ tự triển khai
1. Pha 1 (Postgres compat) — tôi code, test local vẫn chạy SQLite.
2. Pha 2 (R2 backend) — tôi code, test với R2 creds của bạn.
3. Pha 3 (READ_ONLY) — tôi code.
4. Pha 4 (Vercel + Git) — tôi code + bạn tạo repo/account.
5. Pha 5 (migrate) — chạy khi DB Postgres + R2 sẵn.

## File chạm
- `app.py`, `config.py`, `services/poster_cache.py` (+ r2 uploader mới), `routes.py`, `templates/index.html`
- mới: `vercel.json`, `wsgi.py`, `requirements-vercel.txt`, `scripts/migrate_sqlite_to_postgres.py`, `scripts/upload_posters_to_r2.py`

## Câu hỏi mở
1. R2: bucket public qua custom domain hay `*.r2.dev`? (r2.dev đơn giản hơn cho MVP).
2. Vercel Postgres: dùng connection string đơn hay pooled (pooled khuyên cho serverless).
3. Local sau deploy: giữ SQLite hay chuyển hẳn local sang Postgres luôn? (kế hoạch: local vẫn SQLite khi dev nhanh; bật Postgres khi sync).
