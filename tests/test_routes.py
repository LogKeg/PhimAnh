# tests/test_routes.py
"""Kiểm tra route trang chủ, chi tiết phim, gieo hạt theo năm (mock collector)."""
from models import Movie
from queries import upsert_movie
from routes import bp  # noqa: F401  (đảm bảo blueprint import được)
from services import collector


def test_index_empty(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "còn trống" in resp.get_data(as_text=True)


def test_movie_detail_404(client):
    assert client.get("/movie/999").status_code == 404


def test_seed_route_uses_collector(client, app, monkeypatch):
    called = {}

    def fake_seed(year, limit=50):
        called["year"] = year
        called["limit"] = limit
        upsert_movie({"wikidata_id": "Q10", "title": "Seed A", "year": str(year)})
        return ["Seed A"], [], 1, []

    monkeypatch.setattr(collector, "seed_by_year", fake_seed)

    resp = client.post(
        "/", data={"action": "seed", "year": "2022", "limit": "5"}, follow_redirects=True
    )
    assert resp.status_code == 200
    assert called == {"year": 2022, "limit": 5}
    with app.app_context():
        assert Movie.query.count() == 1
        assert Movie.query.first().title == "Seed A"
