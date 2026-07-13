# tests/test_queries.py
"""Kiểm tra upsert (dedup theo wikidata_id), giá trị lọc, tìm kiếm + phân trang."""
from models import Movie
from queries import get_filter_values, query_movies, upsert_movie


def test_upsert_create_then_update(app):
    rec = {"wikidata_id": "Q1", "imdb_id": "tt1", "title": "Phim A", "year": "2020", "genre": "Drama"}
    movie, created = upsert_movie(rec)
    assert created and movie.title == "Phim A"

    # Cùng wikidata_id → cập nhật, không tạo mới
    rec2 = {"wikidata_id": "Q1", "title": "Phim A", "country": "USA"}
    movie2, created2 = upsert_movie(rec2)
    assert not created2
    assert movie2.id == movie.id
    assert movie2.country == "USA"
    assert Movie.query.count() == 1


def test_get_filter_values(app):
    upsert_movie({"wikidata_id": "Q1", "title": "A", "genre": "Drama, Crime",
                  "country": "USA", "actors": "X, Y", "year": "2020"})
    upsert_movie({"wikidata_id": "Q2", "title": "B", "genre": "Comedy",
                  "country": "VN", "actors": "Z", "year": "2021"})
    values = get_filter_values()
    assert "Drama" in values["genres"] and "Comedy" in values["genres"]
    assert "USA" in values["countries"] and "VN" in values["countries"]
    assert set(values["years"]) == {"2020", "2021"}


def test_query_filter_and_pagination(app):
    for i in range(15):
        upsert_movie({"wikidata_id": f"Q{i}", "title": f"M{i}", "genre": "Action", "year": "2021"})

    page1 = query_movies(sort_by="genre", filter_value="Action", page=1, per_page=12)
    assert page1.total == 15 and len(page1.items) == 12
    page2 = query_movies(sort_by="genre", filter_value="Action", page=2, per_page=12)
    assert len(page2.items) == 3

    found = query_movies(search_text="M3")
    assert any(m.title == "M3" for m in found.items)

    actor = query_movies(actor_name="Nobody")
    assert actor.total == 0


def test_year_filter_exact(app):
    upsert_movie({"wikidata_id": "Q1", "title": "A", "year": "2019"})
    upsert_movie({"wikidata_id": "Q2", "title": "B", "year": "2020"})
    result = query_movies(sort_by="year", filter_value="2020", per_page=50)
    assert result.total == 1 and result.items[0].title == "B"


def test_order_newest_oldest_title(app):
    upsert_movie({"wikidata_id": "Q1", "title": "Alpha", "year": "2010"})
    upsert_movie({"wikidata_id": "Q2", "title": "Beta", "year": "2020"})
    upsert_movie({"wikidata_id": "Q3", "title": "Gamma", "year": "2000"})
    newest = [m.title for m in query_movies(order="newest", per_page=50).items]
    assert newest[0] == "Beta"               # 2020 đầu
    oldest = [m.title for m in query_movies(order="oldest", per_page=50).items]
    assert oldest[0] == "Gamma"              # 2000 đầu
    by_title = [m.title for m in query_movies(order="title", per_page=50).items]
    assert by_title[0] == "Alpha"            # A–Z
