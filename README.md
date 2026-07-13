# Ứng dụng phim ảnh

Ứng dụng web **tự thu thập thông tin phim từ Wikidata + Wikipedia** — **không cần API key**, không phụ thuộc dịch vụ bên thứ ba thương mại. Dữ liệu mở, hợp pháp. Lưu vào SQLite.

> Đã **bỏ điểm IMDb/Rotten Tomatoes** (dữ liệu độc quyền — chỉ lấy được qua API thương mại hoặc cào web viển ToS).

## Tính năng
- **Thu thập phim** theo tên (tra Wikidata → điền đủ thông tin + nội dung từ Wikipedia)
- **Gieo hạt hàng loạt theo năm**: nạp nhiều phim ra mắt trong 1 năm cùng lúc
- Thông tin: tên, năm, ngày ra mắt, thể loại, quốc gia, ngôn ngữ, đạo diễn, diễn viên, thời lượng, nội dung, poster
- **Link xem phim** (URL tìm kiếm JustWatch theo vùng) + link IMDb
- **Poster IMDb** (tuỳ chọn): scraper headless Chromium lấy `og:image` cho phim thiếu ảnh — viển ToS IMDb, chỉ dùng cá nhân
- **Poster cache local**: mọi poster (IMDb/Wikipedia/Wikidata) được tải về `static/posters/` để tránh phụ thuộc hotlink/gãy link; tự lấy IMDb khi gieo hạt
- Sắp xếp/lọc theo **thể loại, quốc gia, diễn viên, năm** (dropdown động từ dữ liệu thật)
- Tìm kiếm theo **tên phim** hoặc **diễn viên**
- Phân trang
- **Lazy enrich**: phim gieo hạt sẽ tự lấy nội dung + poster từ Wikipedia khi mở trang chi tiết

## Cấu trúc mã
```
app.py              # entry point: tạo app, khởi tạo DB, auto-migrate
config.py           # cấu hình từ biến môi trường
extensions.py       # instance SQLAlchemy (tránh phụ thuộc vòng)
models.py           # model Movie + helper tách chuỗi
queries.py          # upsert, giá trị lọc, tìm/lọc/phân trang
routes.py           # blueprint: trang chủ + chi tiết phim
services/
  wikidata.py       # SPARQL + wbsearchentities (nguồn cấu trúc chính)
  wikipedia.py      # REST summary (nội dung + poster)
  collector.py      # lắp ghép bản ghi + gieo hạt + lazy enrich
templates/ static/  # giao diện
tests/              # pytest: queries, collector (mock), routes
```

## Cài đặt
1. Python 3.9+
2. Tạo môi trường ảo + cài dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt           # base (chạy được cả Vercel)
pip install -r requirements-local.txt     # + playwright (IMDb poster) + boto3 (R2)
pip install -r requirements-dev.txt       # test
playwright install chromium               # nếu dùng scraper IMDb
```

3. (Tuỳ chọn) cấu hình `.env`:

```bash
cp .env.example .env
# sửa WIKI_LANG, WATCH_REGION nếu muốn (mặc định vi / vn)
```

> **Không cần đăng ký API key nào.** Dữ liệu lấy trực tiếp từ Wikidata/Wikipedia (dữ liệu mở).

## Deploy lên Vercel (online read-only)
Kiến trúc: cào data ở **local** → ghi vào **Vercel Postgres** + poster lên **Cloudinary**; Vercel chạy **read-only**.

1. Push repo lên GitHub (private).
2. Vercel: import repo → tự nhận Flask qua `vercel.json` + `api/index.py`.
3. Tạo **Vercel Postgres** (Storage → Postgres → Connect to project; app tự đọc `POSTGRES_*`).
4. Tạo **Cloudinary** (free, không cần thẻ): lấy `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`.
5. Set env trên Vercel: `FLASK_SECRET_KEY`, `READ_ONLY=true`, `POSTER_BACKEND=cloudinary`,
   `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` (DB tự inject `POSTGRES_*`).
6. Ở local (set cùng env + `DATABASE_URL`=Postgres, `READ_ONLY` bỏ trống):
   - `python3 scripts/migrate_sqlite_to_postgres.py` — chuyển ~11k phim sang Postgres.
   - `python3 scripts/upload_posters_to_cloudinary.py` — đẩy poster local lên Cloudinary.
   - Sau đó cào thêm (seed/poster/plot) ghi thẳng Postgres + Cloudinary.

> Poster backend (qua `POSTER_BACKEND`): `local` (dev), `cloudinary` (online/khuyên), `r2` (có thẻ), `remote` (giữ URL gốc).
> Vercel là serverless: KHÔNG chạy được background thread / Playwright → mọi cào phải ở local.


## Chạy
```bash
python app.py
# mở http://localhost:5000
```
> macOS hay chiếm port 5000 cho AirPlay → chạy `PORT=8000 python app.py` nếu lỗi.

## Sử dụng
- **Gieo hạt**: nhập năm + số lượng → nút "Gieo hạt" để nạp nhiều phim của năm đó.
- **Thu thập 1 phim**: nhập tên → "Thu thập".
- **Tìm/lọc**: ô tên/diễn viên + chọn kiểu lọc → dropdown giá trị lọc tự nạp.

## Kiểm thử
```bash
pytest -q
```

## Lưu ý / giới hạn
- **Không có điểm IMDb/RT** (đã bỏ theo thiết kế). Có thể bổ sung sau bằng cào web, nhưng viển ToS.
- **Link xem phim** là URL tìm kiếm JustWatch (tự ghép), không phải link streaming trực tiếp.
- Hình ảnh poster lấy từ Wikipedia thumbnail / Wikimedia Commons (P18).
- Gieo hạt 1 năm truy vấn 1 SPARQL duy nhất; nội dung từng phim được bổ sung lazily khi xem.
