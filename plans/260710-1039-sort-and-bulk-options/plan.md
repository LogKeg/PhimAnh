# Kế hoạch: Sắp xếp theo thời gian + tuỳ chọn cào lớn

## Kế hoạch 1 — Sắp xếp phim theo ngày ra mắt (mới nhất đầu)

### Bối cảnh
- Hiện `query_movies` xếp theo `title` A–Z. Cột `year` (chuỗi 4 số) + `released` (ISO `YYYY-MM-DD` từ Wikidata) đủ để xếp thời gian.

### Thay đổi
1. **queries.query_movies**: thêm tham số `order` (mặc định `"newest"`):
   - `newest`: `year DESC NULLS LAST, released DESC NULLS LAST, title`
   - `oldest`: ngược lại
   - `title`: `title ASC` (giữ cũ)
   - `year` dạng chuỗi 4 số → xếp lexicographic = thời gian.
2. **routes**: đọc `order` từ `request.args`, truyền vào `query_movies`; giữ qua phân trang.
3. **index.html**: thêm select **"Thứ tự"** (Mới nhất / Cũ nhất / Tên A–Z) cạnh bộ lọc; đưa `order` vào mọi link phân trang + hidden fields.

### File chạm
- `queries.py`, `routes.py`, `templates/index.html`

### Tiêu chí
- Mặc định trang chủ: phim mới nhất đầu.
- Chuyển thứ tự → danh sách đổi, phân trang giữ thứ tự.

---

## Kế hoạch 2 — Tuỳ chọn khi cào lớn (mô tả / poster)

### Bối cảnh
- "Cào lớn" hiện luôn: metadata + ảnh Wikidata (poster), KHÔNG lấy mô tả. Không có lựa chọn.

### Thay đổi
1. **collector.build_record**: thêm `with_poster=True`. `with_poster=False` → bỏ qua cache ảnh (chỉ metadata, nhanh nhất).
2. **bulk.seed_work**: thêm `with_plot=False, with_poster=True`:
   - `build_record(partial, full=False, with_poster=with_poster)`.
   - Nếu `with_plot`: sau khi seed, gọi `fetch_missing_plots` cho phim mới (lấy Wikipedia vi→en).
3. **routes seed_bulk**: đọc `with_plot`, `with_poster` (checkbox) từ form → truyền `seed_work`.
4. **index.html**: form "Cào lớn" thêm 2 checkbox:
   - `☑ Lấy ảnh Wikidata (nhanh)` — mặc định bật.
   - `☐ Lấy mô tả Wikipedia (chậm hơn)` — mặc định tắt.
   - (IMDb poster vẫn dùng nút riêng — quá chậm cho cào lớn.)

### File chạm
- `services/collector.py`, `services/bulk.py`, `routes.py`, `templates/index.html`

### Tiêu chí
- Bỏ tick "ảnh Wikidata" → cào chỉ metadata (nhanh nhất, không ảnh).
- Bật "mô tả" → sau seed tự lấy plot cho phim mới.
- Mặc định giữ hành vi cũ (ảnh có, mô tả không) để không phá thói quen.

---

## Triển khai chung
- Làm Kế hoạch 1 trước (nhỏ, độc lập), test, rồi Kế hoạch 2.
- pytest: thêm test `order` + `with_poster/with_plot`.
- KHÔNG xoá DB; server restart giữ data.

## Câu hỏi mở
1. Kế hoạch 1: chỉ đổi mặc định "mới nhất" (không thêm select) hay thêm select đầy đủ (mới/cũ/A-Z)? — kế hoạch chọn select đầy đủ.
2. Kế hoạch 2: IMDb poster có nên thành checkbox thứ 3 (kèm cảnh báo rất chậm) trong form cào lớn, hay giữ nút riêng? — kế hoạch giữ nút riêng.
