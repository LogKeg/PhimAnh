# models.py
"""Model Movie: thông tin phim thu thập từ Wikidata/Wikipedia (không cần key).

Lưu ý: các trường mô tả dùng db.Text (không giới hạn độ dài) để tương thích
Postgres (VARCHAR(N) ở Postgres ÉP độ dài, khác SQLite)."""
from datetime import datetime

from extensions import db


def _split_csv(value):
    """Tách chuỗi phân cách dấu phẩy, bỏ khoảng trắng và rỗng."""
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


class Movie(db.Model):
    __tablename__ = "movies"

    id = db.Column(db.Integer, primary_key=True)
    wikidata_id = db.Column(db.String(32), index=True)
    imdb_id = db.Column(db.String(32), index=True)
    title = db.Column(db.Text, nullable=False)
    year = db.Column(db.String(16))
    released = db.Column(db.Text)
    genre = db.Column(db.Text)
    director = db.Column(db.Text)
    actors = db.Column(db.Text)
    country = db.Column(db.Text)
    language = db.Column(db.Text)
    runtime = db.Column(db.String(32))
    plot = db.Column(db.Text)
    poster_url = db.Column(db.Text)
    wiki_title = db.Column(db.Text)
    imdb_url = db.Column(db.Text)
    watch_link = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ---- Helpers hiển thị / lọc ----
    def get_genres(self):
        return _split_csv(self.genre)

    def get_actors(self):
        return _split_csv(self.actors)

    def get_countries(self):
        return _split_csv(self.country)
