# routes.py
"""Blueprint: trang chủ (thu thập/gieo hạt theo năm/tìm/lọc) + chi tiết phim."""
from flask import (Blueprint, current_app, render_template, request, redirect,
                   url_for, flash, jsonify)

from config import READ_ONLY
from models import Movie
from queries import get_filter_values, query_movies, upsert_movie
from services import bulk, collector

bp = Blueprint("main", __name__)

# Trường filter cần giữ lại khi chuyển hướng sau POST
_FILTER_KEYS = ("search_text", "actor_name", "sort_by", "filter_value", "order")


def _filter_args(source):
    """Lấy các tham số lọc/tìm kiếm từ request (GET hoặc form ẩn)."""
    return {key: source.get(key, "") for key in _FILTER_KEYS}


@bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if READ_ONLY:
            flash("Chế độ read-only (online) — cào dữ liệu chỉ chạy ở local.", "warning")
            return redirect(url_for("main.index", **_filter_args(request.form)))
        return _handle_post()

    args = _filter_args(request.args)
    page = request.args.get("page", 1, type=int)
    order = request.args.get("order", "newest")
    pagination = query_movies(
        search_text=args["search_text"] or None,
        actor_name=args["actor_name"] or None,
        sort_by=args["sort_by"] or None,
        filter_value=args["filter_value"] or None,
        order=order,
        page=page,
    )
    return render_template(
        "index.html",
        movies=pagination.items,
        pagination=pagination,
        filters=get_filter_values(),
        read_only=READ_ONLY,
        **args,
    )


def _handle_post():
    """Xử lý 2 hành động: collect (theo tên) hoặc seed (theo năm)."""
    action = request.form.get("action")
    redirect_args = _filter_args(request.form)

    if action == "collect":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Vui lòng nhập tên phim để thu thập.", "warning")
        else:
            record, err = collector.collect_by_title(title)
            if err:
                flash(err, "danger")
            else:
                movie, created = upsert_movie(record)
                verb = "Đã thêm" if created else "Đã cập nhật"
                flash(f"{verb} '{movie.title}'.", "success")

    elif action == "seed":
        try:
            year = int(request.form.get("year", "").strip())
        except ValueError:
            flash("Năm không hợp lệ.", "warning")
            return redirect(url_for("main.index", **redirect_args))
        try:
            limit = max(1, min(int(request.form.get("limit", "30")), 100))
        except ValueError:
            limit = 30
        added, skipped, posters, errors = collector.seed_by_year(year, limit)
        flash(
            f"Gieo hạt năm {year}: +{len(added)} phim mới, {len(skipped)} đã có, "
            f"{posters} poster IMDb.",
            "success",
        )
        for msg in errors[:5]:
            flash(msg, "warning")

    elif action == "enrich_posters":
        try:
            limit = max(1, min(int(request.form.get("limit", "100")), 500))
        except ValueError:
            limit = 100
        ok, message = bulk.start(
            "posters", "Lấy poster IMDb",
            bulk.poster_work(current_app._get_current_object(), limit),
        )
        flash(message, "success" if ok else "warning")

    elif action == "enrich_plots":
        try:
            limit = max(1, min(int(request.form.get("limit", "5000")), 5000))
        except ValueError:
            limit = 5000
        ok, message = bulk.start(
            "plots", "Lấy mô tả",
            bulk.plot_work(current_app._get_current_object(), limit),
        )
        flash(message, "success" if ok else "warning")

    elif action == "seed_bulk":
        try:
            start_year = int(request.form.get("start_year", ""))
            end_year = int(request.form.get("end_year", ""))
            per_year = max(1, min(int(request.form.get("per_year", "100")), 500))
        except ValueError:
            flash("Năm không hợp lệ.", "warning")
            return redirect(url_for("main.index", **redirect_args))
        if end_year < start_year:
            start_year, end_year = end_year, start_year
        with_poster = request.form.get("with_poster") == "on"      # checkbox (mặc định bật)
        with_plot = request.form.get("with_plot") == "on"          # checkbox (mặc định tắt)
        ok, message = bulk.start(
            "seed", "Cào phim",
            bulk.seed_work(current_app._get_current_object(), start_year, end_year,
                           per_year, with_plot=with_plot, with_poster=with_poster),
        )
        flash(message, "success" if ok else "warning")

    return redirect(url_for("main.index", **redirect_args))


@bp.route("/seed-status")
def seed_status():
    """Trả tiến độ job cào ngầm dạng JSON (cho AJAX poll)."""
    return jsonify(bulk.status())


@bp.route("/movie/<int:movie_id>")
def movie_detail(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    # Lazy enrich: nếu thiếu nội dung/poster, thử lấy (Wikipedia → IMDb)
    collector.enrich_movie(movie)
    return render_template("movie_detail.html", movie=movie)
