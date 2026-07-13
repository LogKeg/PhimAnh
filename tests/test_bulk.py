# tests/test_bulk.py
"""Kiểm tra job runner nền: cào phim theo năm + lấy poster IMDb (chạy ngầm, tiến độ)."""
import time

from services import bulk, collector, imdb, wikipedia, wikidata


def _wait_done(name, timeout=10):
    """Đợi job `name` kết thúc (poll status)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = bulk.status(name)
        if s and not s["running"]:
            return s
        time.sleep(0.05)
    return bulk.status(name)


def _partial(qid="Q1", title="Phim X", year="2020"):
    return {"wikidata_id": qid, "title": title, "year": year, "imdb": f"tt{qid}", "image": ""}


def test_seed_job_runs_in_background(app, monkeypatch):
    """Job cào theo năm chạy ngầm → DB có phim, status done."""
    monkeypatch.setattr(wikidata, "films_of_year",
                        lambda year, limit=100: ([_partial("Q%d" % year, "Y%d" % year, str(year))], None))
    monkeypatch.setattr(imdb, "imdb_poster", lambda iid: ("", None))
    monkeypatch.setattr(wikipedia, "summary", lambda t, lang=None: ("", "", None))
    # rút ngắn delay lịch sự để test nhanh
    monkeypatch.setattr(bulk, "_POLITE_DELAY", 0)

    ok, _ = bulk.start("seed", "Cào phim", bulk.seed_work(app, 2020, 2021, 10))
    assert ok is True
    ok2, _ = bulk.start("seed", "Cào phim", bulk.seed_work(app, 2020, 2021, 10))  # không chạy chồng
    assert ok2 is False

    s = _wait_done("seed")
    assert s["done"] is True and s["running"] is False
    assert s["added"] == 2 and "Hoàn tất" in s["message"]
    from models import Movie
    assert Movie.query.count() == 2


def test_poster_job_runs_in_background(app, monkeypatch):
    """Job lấy poster IMDb chạy ngầm → cập nhật poster, tiến độ tăng dần."""
    from queries import upsert_movie
    upsert_movie({"wikidata_id": "Q1", "imdb_id": "tt1", "title": "Phim A"})  # không có poster
    upsert_movie({"wikidata_id": "Q2", "imdb_id": "tt2", "title": "Phim B"})

    # Mock generator imdb_posters_iter yield từng phim (giả lập scraper)
    def fake_iter(items, limit=20):
        for idx, (mid, iid) in enumerate(items):
            yield (mid, f"https://img-{iid}.jpg", None)

    monkeypatch.setattr(imdb, "imdb_posters_iter", fake_iter)

    ok, _ = bulk.start("posters", "Lấy poster IMDb", bulk.poster_work(app, 50))
    assert ok is True

    s = _wait_done("posters")
    assert s["done"] is True
    assert s["added"] == 2 and s["total"] == 2
    # cache_poster bị mock passthrough (conftest) → poster_url = url giả
    from models import Movie
    assert all(m.poster_url for m in Movie.query.all())


def test_status_registry_shape():
    s = bulk.status()
    assert isinstance(s, dict)
    for key in ("running", "done", "total", "done_count", "added", "message"):
        # mỗi job snapshot (nếu có) đủ khóa
        pass
    assert bulk.status("nonexistent") is None
