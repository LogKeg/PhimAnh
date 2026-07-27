# queries.py
"""Truy vấn/ghi Movie: upsert, giá trị lọc, tìm kiếm + lọc + phân trang."""
from extensions import db
from models import Movie

PER_PAGE = 12

# Trường được ghi từ record dict (thu thập) vào Movie
RECORD_FIELDS = (
    "wikidata_id", "imdb_id", "title", "year", "released", "genre", "director",
    "actors", "country", "language", "runtime", "plot", "poster_url",
    "wiki_title", "imdb_url", "watch_link",
)


def upsert_movie(record):
    """Thêm mới hoặc cập nhật phim theo wikidata_id/imdb_id. Trả về (movie, created)."""
    movie = _find_existing(record)
    if movie:
        _apply(movie, record)
        db.session.commit()
        return movie, False

    movie = Movie()
    _apply(movie, record)
    if not movie.title:
        return movie, False
    db.session.add(movie)
    db.session.commit()
    return movie, True


def _find_existing(record):
    """Tìm phim đã có theo wikidata_id trước, rồi tới imdb_id."""
    if record.get("wikidata_id"):
        found = Movie.query.filter_by(wikidata_id=record["wikidata_id"]).first()
        if found:
            return found
    if record.get("imdb_id"):
        found = Movie.query.filter_by(imdb_id=record["imdb_id"]).first()
        if found:
            return found
    return None


def _apply(movie, record):
    """Gán các trường từ record dict vào movie object."""
    for field in RECORD_FIELDS:
        if field in record and record[field] is not None:
            setattr(movie, field, record[field])


def get_filter_values():
    """Tập hợp giá trị duy nhất từ DB để render dropdown lọc."""
    genres, countries, actors, years = set(), set(), set(), set()
    for movie in Movie.query.all():
        genres.update(movie.get_genres())
        countries.update(movie.get_countries())
        actors.update(movie.get_actors())
        if movie.year:
            years.add(movie.year)
    return {
        "genres": sorted(g for g in genres if g),
        "countries": sorted(c for c in countries if c),
        "actors": sorted(a for a in actors if a),
        "years": sorted(y for y in years if y),
    }


def query_movies(search_text=None, actor_name=None, sort_by=None,
                 filter_value=None, order="newest", page=1, per_page=PER_PAGE):
    """Tìm + lọc + phân trang phim theo tiêu đề/diễn viên/điều kiện lọc."""
    query = Movie.query
    if search_text:
        query = query.filter(Movie.title.ilike(f"%{search_text}%"))
    if actor_name:
        query = query.filter(Movie.actors.ilike(f"%{actor_name}%"))
    if filter_value:
        if sort_by == "genre":
            query = query.filter(Movie.genre.ilike(f"%{filter_value}%"))
        elif sort_by == "country":
            query = query.filter(Movie.country.ilike(f"%{filter_value}%"))
        elif sort_by == "actor":
            query = query.filter(Movie.actors.ilike(f"%{filter_value}%"))
        elif sort_by == "year":
            query = query.filter(Movie.year == filter_value)
    query = query.order_by(*_order_clause(order))
    return query.paginate(page=page, per_page=per_page, error_out=False)


def _order_clause(order):
    """Mệnh đề ORDER BY theo lựa chọn thứ tự (mặc định: mới nhất đầu).

    Dùng cờ (year IS NULL) để đẩy phim thiếu năm xuống cuối (SQLite không hỗ trợ NULLS LAST).
    """
    year, released, title = Movie.year, Movie.released, Movie.title
    nulls_last = year.is_(None).asc()           # non-null (0) trước null (1) → null cuối
    if order == "oldest":
        return nulls_last, year.asc(), released.asc(), title.asc()
    if order == "title":
        return (title.asc(),)
    if order == "rating":
        # điểm cao → thấp, phim thiếu điểm đẩy cuối, tie-break theo năm giảm dần
        return Movie.imdb_rating.is_(None).asc(), Movie.imdb_rating.desc(), year.desc()
    # newest (mặc định): năm giảm dần → ngày giảm dần → tên
    return nulls_last, year.desc(), released.desc(), title.asc()
