# models.py
"""Model Movie: thông tin phim thu thập từ Wikidata/Wikipedia (không cần key)."""
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
    wikidata_id = db.Column(db.String(32), index=True)  # Q-id, để khử trùng
    imdb_id = db.Column(db.String(32), index=True)       # lấy từ Wikidata P345
    title = db.Column(db.String(256), nullable=False)
    year = db.Column(db.String(16))
    released = db.Column(db.String(64))
    genre = db.Column(db.String(256))
    director = db.Column(db.String(256))
    actors = db.Column(db.String(512))
    country = db.Column(db.String(256))
    language = db.Column(db.String(128))
    runtime = db.Column(db.String(32))
    plot = db.Column(db.Text)
    poster_url = db.Column(db.String(256))
    wiki_title = db.Column(db.String(256))  # tiêu đề bài Wikipedia (vi) để enrich nội dung
    imdb_url = db.Column(db.String(256))
    watch_link = db.Column(db.String(256))  # URL tìm kiếm JustWatch theo vùng
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ---- Helpers hiển thị / lọc ----
    def get_genres(self):
        return _split_csv(self.genre)

    def get_actors(self):
        return _split_csv(self.actors)

    def get_countries(self):
        return _split_csv(self.country)
