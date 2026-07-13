# services/collector.py
"""Lắp ghép bản ghi phim: Wikidata (cấu trúc) + Wikipedia (nội dung) + IMDb (poster).
Poster luôn được tải về cache local (static/posters/). Không cần key."""
from urllib.parse import quote

from config import WATCH_REGION
from queries import upsert_movie
from services import imdb, poster_cache, wikipedia, wikidata


def build_record(partial, full=True, with_poster=True):
    """Bổ sung nội dung + poster + link vào partial record Wikidata.

    full=True (thu thập 1 phim): gọi Wikipedia lấy nội dung + poster IMDb.
    full=False (gieo hạt hàng loạt): bỏ qua Wikipedia/IMDb để nhanh; ảnh Wikidata nếu with_poster.
    """
    rec = dict(partial)
    # Chuẩn hoá tên trường từ partial Wikidata → field của model Movie
    rec.setdefault("imdb_id", rec.get("imdb", ""))
    if rec.get("imdb_id"):
        rec.setdefault("imdb_url", f"https://www.imdb.com/title/{rec['imdb_id']}/")
    rec.setdefault("wiki_title", rec.get("vi_title", ""))
    rec.setdefault("plot", "")
    rec.setdefault("watch_link", _justwatch_url(rec.get("title")))

    if not full:
        # Gieo hạt: ảnh Wikidata (nếu with_poster), bỏ qua nội dung
        rec["poster_url"] = _localize(rec.get("image", ""), rec) if with_poster else ""
        return rec

    # Nội dung từ Wikipedia (ưu tiên vi, fallback en)
    title = rec.get("vi_title") or rec.get("title")
    extract, thumb, _ = wikipedia.summary(title, "vi")
    if not extract and rec.get("en_title"):
        extract, thumb, _ = wikipedia.summary(rec["en_title"], "en")
    if extract:
        rec["plot"] = extract
    # Poster ưu tiên IMDb (canonical) → thumbnail Wikipedia → ảnh Wikidata → cache local
    poster = ""
    if rec.get("imdb_id"):
        poster, _ = imdb.imdb_poster(rec["imdb_id"])
    if not poster:
        poster = thumb
    if not poster:
        poster = rec.get("image", "")
    rec["poster_url"] = _localize(poster, rec)
    return rec


def enrich_movie(movie):
    """Lazy enrich khi xem chi tiết: nội dung từ Wikipedia; poster IMDb→Wikipedia→local."""
    title = movie.wiki_title or movie.title
    changed = False
    # Nội dung (nếu thiếu) từ Wikipedia
    if not movie.plot and title:
        extract, _, _ = wikipedia.summary(title, "vi")
        if extract:
            movie.plot = extract
            changed = True
    # Poster (nếu thiếu): IMDb trước, rồi tới Wikipedia, rồi cache local
    if not movie.poster_url:
        poster = ""
        if movie.imdb_id:
            poster, _ = imdb.imdb_poster(movie.imdb_id)
        if not poster and title:
            _, thumb, _ = wikipedia.summary(title, "vi")
            poster = thumb
        if poster:
            movie.poster_url = _localize(poster, movie)
            changed = True
    if changed:
        from extensions import db
        db.session.commit()


def fetch_missing_plots(limit=100, progress=None, movies=None):
    """Điền plot (mô tả) cho phim thiếu: Wikipedia vi → en. Trả về (updated, total, errors).

    movies: nếu truyền vào, xử lý đúng danh sách đó (vd. phim vừa seed); ngược lại query phim thiếu.
    progress(done, total, updated) được gọi sau mỗi phim (cho tiến độ sống, tuỳ chọn).
    """
    from extensions import db
    from models import Movie
    if movies is None:
        movies = (
            Movie.query
            .filter((Movie.plot.is_(None)) | (Movie.plot == ""))
            .limit(limit)
            .all()
        )
    missing = movies
    total = len(missing)
    if progress:
        progress(0, total, 0)
    if not missing:
        return 0, 0, []
    # Nhóm không có wiki_title vi → resolve tiêu đề bài en qua SPARQL (chunk 100 QID)
    qids_b = [m.wikidata_id for m in missing if not m.wiki_title and m.wikidata_id]
    en_map = {}
    for i in range(0, len(qids_b), 100):
        mapping, _err = wikidata.en_titles_for_qids(qids_b[i:i + 100])
        if mapping:
            en_map.update(mapping)
    updated, errors, done = 0, [], 0
    for m in missing:
        extract = ""
        if m.wiki_title:                                  # ưu tiên tiếng Việt
            extract, _, _ = wikipedia.summary(m.wiki_title, "vi")
        if not extract and en_map.get(m.wikidata_id):    # fallback tiếng Anh
            extract, _, _ = wikipedia.summary(en_map[m.wikidata_id], "en")
        if extract:
            m.plot = extract
            updated += 1
        done += 1
        if progress:
            progress(done, total, updated)
        if done % 20 == 0:                                # commit lô giữ tiến độ
            db.session.commit()
    db.session.commit()
    return updated, total, errors


def fetch_missing_posters(limit=20, progress=None):
    """Lấy + cache poster IMDb cho phim thiếu ảnh. Trả về (updated, total, errors).

    progress(done, total, updated) được gọi sau mỗi phim (cho tiến độ sống, tuỳ chọn).
    """
    from extensions import db
    from models import Movie
    missing = (
        Movie.query
        .filter((Movie.poster_url.is_(None)) | (Movie.poster_url == ""))
        .filter(Movie.imdb_id.isnot(None), Movie.imdb_id != "")
        .limit(limit)
        .all()
    )
    targets = [(m.id, m.imdb_id) for m in missing]
    by_id = {m.id: m for m in missing}
    total = len(targets)
    if progress:
        progress(0, total, 0)
    if not targets:
        return 0, 0, []
    updated, errors, done = 0, [], 0
    for movie_id, url, err in imdb.imdb_posters_iter(targets, limit=total):
        done += 1
        if url and movie_id in by_id:
            by_id[movie_id].poster_url = _localize(url, by_id[movie_id])
            updated += 1
        elif err:
            errors.append(err)
        if progress:
            progress(done, total, updated)
        if done % 20 == 0:           # commit từng lô để giữ tiến độ nếu bị gián đoạn
            db.session.commit()
    db.session.commit()
    return updated, total, errors


def collect_by_title(title):
    """Tìm theo tên → phim phù hợp nhất → bản ghi đầy đủ.

    Thứ tự: nhãn Wikidata (vi → en) → fallback tra bài Wikipedia ra QID (cho tên tiếng Việt).
    """
    qids, err = wikidata.search_entities(title, "vi")
    if not qids:
        qids, err = wikidata.search_entities(title, "en")
    if err:
        return None, err
    if not qids:
        # Fallback: tên tiếng Việt thường là tiêu đề bài Wikipedia, không phải nhãn Wikidata
        for lang in ("vi", "en"):
            qid, _ = wikipedia.resolve_qid(title, lang)
            if qid:
                qids = [qid]
                break
    if not qids:
        return None, f"Không tìm thấy phim '{title}'."
    films, err = wikidata.films_by_qids(qids)
    if err:
        return None, err
    if not films:
        return None, f"'{title}' không phải phim (theo Wikidata)."
    return build_record(films[0], full=True), None


def seed_by_year(year, limit=50):
    """Gieo hạt tất cả phim của 1 năm từ Wikidata + tự lấy poster IMDb.

    Trả về (added, skipped, posters, errors).
    """
    films, err = wikidata.films_of_year(year, limit)
    if err:
        return [], [], 0, [err]
    added, skipped, new_movies = [], [], []
    for partial in films:
        rec = build_record(partial, full=False)
        movie, created = upsert_movie(rec)
        name = movie.title or partial.get("title")
        (added if created else skipped).append(name)
        if created:
            new_movies.append(movie)
    # Tự lấy poster IMDb cho phim mới thiếu ảnh
    posters, errors = _enrich_movies(movies=new_movies, limit=len(new_movies), commit=True)
    return added, skipped, posters, errors


# ---------------- helpers ----------------

def _enrich_movies(movies, limit, commit=True):
    """Lấy + cache poster IMDb cho các phim thiếu ảnh (có imdb_id). Trả về (count, errors)."""
    from extensions import db
    from models import Movie  # noqa: F401  (đảm bảo model sẵn sàng trong app context)
    targets = [(m.id, m.imdb_id) for m in movies if m.imdb_id and not m.poster_url]
    if not targets:
        return 0, []
    results = imdb.imdb_posters_bulk(targets, limit=limit)
    by_id = {m.id: m for m in movies}
    count, errors = 0, []
    for movie_id, url, err in results:
        if url and movie_id in by_id:
            by_id[movie_id].poster_url = _localize(url, by_id[movie_id])
            count += 1
        elif err:
            errors.append(err)
    if commit:
        db.session.commit()
    return count, errors


def _localize(remote_url, rec):
    """Cache poster về local; trả về URL local hoặc fallback remote."""
    if not remote_url:
        return ""
    return poster_cache.cache_poster(remote_url, _key(rec))


def _key(rec):
    """Khoá ổn định cho file poster: imdb_id → wikidata_id → title. Chấp nhận dict hoặc Movie."""
    return _field(rec, "imdb_id") or _field(rec, "wikidata_id") or _field(rec, "title") or "x"


def _field(rec, name):
    """Đọc trường từ dict hoặc object."""
    if isinstance(rec, dict):
        return rec.get(name)
    return getattr(rec, name, "")


def _justwatch_url(title):
    """Ghép link tìm kiếm JustWatch theo vùng (không cào, không cần key)."""
    if not title:
        return ""
    return f"https://www.justwatch.com/{WATCH_REGION}/search?q={quote(title)}"
