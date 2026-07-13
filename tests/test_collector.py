# tests/test_collector.py
"""Kiểm tra collector: lắp ghép Wikidata + Wikipedia (mock, không gọi mạng)."""
from services import collector, imdb, wikipedia, wikidata


def _partial():
    """Partial record mô phỏng đầu ra của wikidata._aggregate."""
    return {
        "wikidata_id": "Q25188",
        "title": "Inception",
        "year": "2010",
        "released": "2010-07-15",
        "country": "Hoa Kỳ",
        "director": "Christopher Nolan",
        "genre": "phim khoa học viễn tưởng, phim hành động",
        "actors": "Leonardo DiCaprio, Joseph Gordon-Levitt",
        "language": "tiếng Anh",
        "runtime": "148 min",
        "imdb": "tt1375666",
        "vi_title": "Inception (phim)",
        "en_title": "Inception",
        "image": "https://commons.wikimedia.org/wiki/Special:FilePath/Poster.jpg",
    }


def test_build_record_full_prefers_imdb_poster(monkeypatch):
    monkeypatch.setattr(imdb, "imdb_poster", lambda iid: ("https://imdb-poster.jpg", None))
    monkeypatch.setattr(
        wikipedia, "summary",
        lambda title, lang=None: ("Nội dung tóm tắt phim.", "https://thumb.jpg", None),
    )
    rec = collector.build_record(_partial(), full=True)
    assert rec["poster_url"] == "https://imdb-poster.jpg"  # IMDb ưu tiên hơn Wikipedia
    assert rec["plot"] == "Nội dung tóm tắt phim."


def test_build_record_full_falls_back_to_wikipedia(monkeypatch):
    # IMDb trượt → dùng thumbnail Wikipedia
    monkeypatch.setattr(imdb, "imdb_poster", lambda iid: ("", "không có og:image"))
    monkeypatch.setattr(
        wikipedia, "summary",
        lambda title, lang=None: ("Nội dung tóm tắt phim.", "https://thumb.jpg", None),
    )
    rec = collector.build_record(_partial(), full=True)
    assert rec["imdb_id"] == "tt1375666"
    assert rec["imdb_url"] == "https://www.imdb.com/title/tt1375666/"
    assert rec["wiki_title"] == "Inception (phim)"
    assert rec["poster_url"] == "https://thumb.jpg"
    assert "justwatch.com" in rec["watch_link"]


def test_build_record_bulk_skips_wikipedia(monkeypatch):
    called = {"n": 0}

    def fail(*a, **k):
        called["n"] += 1
        return "", "", None

    monkeypatch.setattr(wikipedia, "summary", fail)
    rec = collector.build_record(_partial(), full=False)
    assert called["n"] == 0              # không gọi Wikipedia khi gieo hạt
    assert rec["plot"] == ""             # chưa có nội dung
    assert rec["poster_url"].endswith("Poster.jpg")  # dùng ảnh Wikidata (cache passthrough)


def test_build_record_bulk_without_poster(monkeypatch):
    """with_poster=False → bỏ qua ảnh, chỉ metadata (cào nhanh nhất)."""
    monkeypatch.setattr(wikipedia, "summary", lambda t, lang=None: ("", "", None))
    rec = collector.build_record(_partial(), full=False, with_poster=False)
    assert rec["poster_url"] == ""       # không lấy ảnh
    assert rec["genre"]                  # metadata vẫn có


def test_fetch_missing_posters_handles_movie_object(app, monkeypatch):
    """_key phải hoạt động với object Movie (không chỉ dict)."""
    from queries import upsert_movie
    upsert_movie({"wikidata_id": "Q1", "imdb_id": "tt1", "title": "Phim A"})  # không có poster
    monkeypatch.setattr(
        imdb, "imdb_posters_iter",
        lambda items, limit=20: [(items[0][0], "https://imdb-x.jpg", None)],
    )
    updated, total, errors = collector.fetch_missing_posters(limit=10)
    assert (updated, total, errors) == (1, 1, [])
    from models import Movie
    assert Movie.query.first().poster_url == "https://imdb-x.jpg"  # cache passthrough


def test_fetch_missing_plots_vi_then_en(app, monkeypatch):
    """Phim có wiki_title → lấy vi; không có → fallback en qua en_titles_for_qids."""
    from queries import upsert_movie
    upsert_movie({"wikidata_id": "Q1", "title": "A", "wiki_title": "Phim A (phim)"})  # có vi
    upsert_movie({"wikidata_id": "Q2", "title": "B"})  # không vi → resolve en

    calls = {"vi": 0, "en": 0}

    def fake_summary(title, lang=None):
        calls[lang] += 1
        return (f"Mô tả {lang} của {title}", "", None)

    monkeypatch.setattr(wikipedia, "summary", fake_summary)
    monkeypatch.setattr(wikidata, "en_titles_for_qids",
                        lambda qids: ({"Q2": "Film B"}, None))

    updated, total, errors = collector.fetch_missing_plots(limit=10)
    assert errors == []
    assert total == 2 and updated == 2
    assert calls["vi"] >= 1 and calls["en"] >= 1   # đã dùng cả vi và en
    from models import Movie
    plots = {m.title: m.plot for m in Movie.query.all()}
    assert "vi" in plots["A"] and "en" in plots["B"]


def test_fetch_missing_plots_no_sources_skipped(app, monkeypatch):
    """Phim không có wiki_title lẫn wikidata_id → bỏ qua, không lỗi."""
    from queries import upsert_movie
    upsert_movie({"wikidata_id": "", "title": "C"})  # không gì để resolve
    monkeypatch.setattr(wikipedia, "summary", lambda t, lang=None: ("", "", None))
    updated, total, errors = collector.fetch_missing_plots(limit=10)
    assert updated == 0 and total == 1


def test_collect_by_title_resolves_film(monkeypatch):
    monkeypatch.setattr(wikidata, "search_entities", lambda t, lang=None: (["Q25188"], None))
    monkeypatch.setattr(wikidata, "films_by_qids", lambda qids: ([_partial()], None))
    monkeypatch.setattr(wikipedia, "summary", lambda t, lang=None: ("", "", None))
    monkeypatch.setattr(imdb, "imdb_poster", lambda iid: ("", None))
    rec, err = collector.collect_by_title("Inception")
    assert err is None
    assert rec["title"] == "Inception"


def test_collect_by_title_not_a_film(monkeypatch):
    monkeypatch.setattr(wikidata, "search_entities", lambda t, lang=None: (["Q12345"], None))
    monkeypatch.setattr(wikidata, "films_by_qids", lambda qids: ([], None))
    rec, err = collector.collect_by_title("XYZ")
    assert rec is None and "không phải phim" in err


def test_collect_by_title_fallback_to_wikipedia(monkeypatch):
    """Khi Wikidata search không ra, dùng Wikipedia resolve_qid (cho tên tiếng Việt)."""
    monkeypatch.setattr(wikidata, "search_entities", lambda t, lang=None: ([], None))
    calls = {}

    def fake_resolve(title, lang):
        calls.setdefault("langs", []).append(lang)
        return ("Q25188", None) if lang == "vi" else ("", None)

    monkeypatch.setattr(wikipedia, "resolve_qid", fake_resolve)
    monkeypatch.setattr(wikidata, "films_by_qids", lambda qids: ([_partial()], None))
    monkeypatch.setattr(wikipedia, "summary", lambda t, lang=None: ("", "", None))
    monkeypatch.setattr(imdb, "imdb_poster", lambda iid: ("", None))
    rec, err = collector.collect_by_title("Kẻ trộm giấc mơ")
    assert err is None
    assert rec["wikidata_id"] == "Q25188"
    assert "vi" in calls["langs"]  # đã dùng fallback Wikipedia


def test_seed_by_year_inserts(app, monkeypatch):
    monkeypatch.setattr(wikidata, "films_of_year", lambda year, limit=50: ([_partial()], None))
    monkeypatch.setattr(wikipedia, "summary", lambda t, lang=None: ("", "", None))
    monkeypatch.setattr(imdb, "imdb_posters_bulk", lambda items, limit=20: [])
    added, skipped, posters, errors = collector.seed_by_year(2010)
    assert errors == []
    assert added == ["Inception"]
    assert skipped == []
    assert posters == 0  # phim đã có ảnh Wikidata → không cần IMDb
