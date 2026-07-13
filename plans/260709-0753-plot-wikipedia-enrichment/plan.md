# Kế hoạch: Lấy mô tả phim (plot) từ Wikipedia

## Bối cảnh
- 4.128 phim trong DB, **0 phim có mô tả** (cào bằng bulk-seed `full=False` nên bỏ qua Wikipedia).
- 561 phim có `wiki_title` (bài Wikipedia vi) → fetch vi được ngay.
- 4.113 phim có `imdb_id`, phần lớn có `wikidata_id` → resolve bài Wikipedia en được.

## Mục tiêu
Điền `plot` cho toàn bộ phim thiếu, ưu tiên tiếng Việt, fallback tiếng Anh. Chạy ngầm, có tiến độ, không cần key, không browser (nhanh).

## Nguồn & chiến lược (đã chốt: Vi → En Wikipedia)
1. Phim có `wiki_title` (vi) → `wikipedia.summary(wiki_title, "vi")` → extract = mô tả vi.
2. Phim KHÔNG có wiki_title nhưng có `wikidata_id` → batch-resolve **en sitelink** (SPARQL `VALUES ?item {…}` + `schema:about`/`schema:isPartOf en.wikipedia.org`) → `wikipedia.summary(en_title, "en")`.
3. Phim không có cả hai → bỏ qua (không IMDb piggyback theo lựa chọn).

## Kiến trúc (tái dùng job runner hiện có)
```
services/wikidata.py   + en_titles_for_qids(qids)  # batch SPARQL → {qid: en_title}
services/collector.py  + fetch_missing_plots(limit, progress)  # vi→en, commit lô 20
services/bulk.py       + plot_work(app, limit)     # job nền, cập nhật done/added sống
routes.py              + action "enrich_plots"     # POST → bulk.start("plots", …)
                        + /seed-status đã trả hết job (gọi chung)
templates/index.html   + nút "Lấy mô tả" + progress area đã đa-job (chỉ thêm 1 form)
```
Job name `"plots"` — song song OK với `"seed"`/`"posters"`.

## Dữ liệu chạy
- `fetch_missing_plots`:
  - Query `Movie.query.filter(plot rỗng).all()` (cap `limit`).
  - Tách 2 nhóm: A= có wiki_title; B= có wikidata_id, không wiki_title.
  - Nhóm A: fetch vi summary từng phim (requests, ~0.3s).
  - Nhóm B: `en_titles_for_qids([qid…])` (1 SPARQL/100 QID) → fetch en summary từng phim.
  - Progress callback `(done, total, added)` → job sống.
  - Commit mỗi 20 phim (giữ tiến độ nếu gián đoạn).

## Pha triển khai
1. **wikidata.en_titles_for_qids**: hàm batch resolve en sitelink. Test mock.
2. **collector.fetch_missing_plots(limit, progress)**: logic vi→en + commit lô. Test mock (vi có/en fallback/bỏ qua).
3. **bulk.plot_work + routes action "enrich_plots" + nút UI**: tái dùng progress area. Test route.
4. **E2E thật**: chạy nhỏ (limit 20) → kiểm plot vào DB; rồi full.

## File chạm
- Sửa: `services/wikidata.py`, `services/collector.py`, `services/bulk.py`, `routes.py`, `templates/index.html`, `tests/` (3 file test).
- Không sửa model (cột `plot` đã có).

## Tiêu chí hoàn thành
- Nút "Lấy mô tả" → job nền, thanh tiến độ vàng hiện `done/total` + `+added` sống.
- Sau chạy: `plot` != rỗng cho phần lớn phim (vi cho 561, en cho ~3.000+ còn lại).
- pytest pass; commit lô 20 → an toàn gián đoạn.
- Không xoá DB/poster.

## Ước tính
~0.5s/phim (requests, không browser) → 4.128 phim ≈ **30–40 phút** nền.

## Rủi ro
- Wikipedia rate-limit nếu fetch dồn dập → thêm sleep nhỏ (0.1s) giữa các request.
- Một số bài vi/en không có `extract` (trang định hướng) → skip, không lỗi.
- SPARQL en_title có thể chậm nếu batch lớn → giữ ≤100 QID/lần.

## Câu hỏi mở
1. **Poster backlog**: 3.809 phim vẫn thiếu poster, IMDb ~20s/phim ≈ **21 giờ** — phi thực tế. Có muốn giảm ưu tiên poster (chỉ IMDb cho top phim quan trọng) hay chấp nhận thiếu?
2. Có muốn lưu riêng **ngôn ngữ** của mô tả (cột `plot_lang`) để UI hiện cờ Vi/En không?
3. Mô tả IMDb `og:description` (English, piggyback cào poster) — bạn đã bỏ qua, nhưng nếu sau này muốn phủ 99% thì bật lại được.
