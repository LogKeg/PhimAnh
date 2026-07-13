# services/bulk.py
"""Trình chạy tác vụ nền (generic): cào phim theo khoảng năm + lấy poster IMDb.

Mỗi job có tên, label, trạng thái (running/done/total/done_count/added/...) chia sẻ
qua registry + lock. Request đọc qua status(), work cập nhật trực tiếp job object.
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List

from services import collector, wikidata

_POLITE_DELAY = 1.0  # giây chờ giữa các năm (lịch sự với Wikidata)


@dataclass
class Job:
    name: str
    label: str
    running: bool = False
    done: bool = False
    total: int = 0          # tổng đơn vị công việc (năm / phim cần poster)
    done_count: int = 0     # đơn vị đã xong
    added: int = 0          # phim mới / poster mới
    skipped: int = 0        # phim trùng
    current: str = ""       # mô tả bước hiện tại
    message: str = ""
    errors: List[str] = field(default_factory=list)


_jobs: Dict[str, Job] = {}
_lock = threading.Lock()


def status(name=None):
    """Snapshot một job (nếu có name) hoặc toàn bộ registry."""
    with _lock:
        if name:
            return _snapshot(_jobs.get(name))
        return {n: _snapshot(j) for n, j in _jobs.items()}


def _snapshot(job):
    if not job:
        return None
    return {
        "name": job.name, "label": job.label, "running": job.running,
        "done": job.done, "total": job.total, "done_count": job.done_count,
        "added": job.added, "skipped": job.skipped, "current": job.current,
        "message": job.message, "errors": list(job.errors),
    }


def start(name, label, work):
    """Khởi động job ngầm chạy work(job). Trả về (ok, message). Trùng tên đang chạy → từ chối."""
    with _lock:
        existing = _jobs.get(name)
        if existing and existing.running:
            return False, f"{existing.label} đang chạy. Vui lòng đợi xong."
        job = Job(name=name, label=label, running=True)
        _jobs[name] = job
    thread = threading.Thread(target=_run, args=(job, work), daemon=True)
    thread.start()
    return True, f"Đã bắt đầu {label}."


def _run(job, work):
    try:
        work(job)
        if not job.message:
            job.message = "Hoàn tất."
    except Exception as exc:  # pylint: disable=broad-except
        job.message = f"Lỗi: {exc}"
        job.errors.append(str(exc))
    finally:
        job.running = False
        job.done = True


# ---------------- work builders ----------------

def seed_work(app, start_year, end_year, per_year, with_plot=False, with_poster=True):
    """Trả về hàm work: cào phim theo khoảng năm. with_poster=ảnh Wikidata, with_plot=lấy mô tả sau."""
    from queries import upsert_movie

    def work(job):
        new_movies = []
        with app.app_context():
            years = end_year - start_year + 1
            job.total = years
            for year in range(start_year, end_year + 1):
                job.current = f"năm {year}/{end_year}"
                films, err = wikidata.films_of_year(year, per_year)
                if err:
                    job.errors.append(f"{year}: {err}")
                    job.done_count += 1
                    continue
                for partial in films:
                    record = collector.build_record(partial, full=False, with_poster=with_poster)
                    movie, created = upsert_movie(record)
                    job.added += 1 if created else 0
                    job.skipped += 0 if created else 1
                    if created:
                        new_movies.append(movie)
                job.done_count += 1
                time.sleep(_POLITE_DELAY)
        # Tuỳ chọn: lấy mô tả Wikipedia cho phim vừa seed
        if with_plot and new_movies:
            job.current = "đang lấy mô tả…"
            def prog(done, total, added):
                job.total = total
                job.done_count = done
                job.current = f"mô tả {done}/{total}"
            with app.app_context():
                collector.fetch_missing_plots(movies=new_movies, progress=prog)
        job.current = ""
        job.message = f"Hoàn tất: +{job.added} phim mới, {job.skipped} trùng."

    return work


def poster_work(app, limit):
    """Trả về hàm work: lấy + cache poster IMDb cho phim thiếu ảnh (chạy ngầm)."""

    def work(job):
        def progress(done, total, added):
            job.total = total
            job.done_count = done
            job.added = added
            job.current = f"{done}/{total} phim" if total else ""

        with app.app_context():
            added, total, errors = collector.fetch_missing_posters(limit=limit, progress=progress)
            job.added = added
            job.errors.extend(errors)
        job.current = ""
        job.message = (f"Hoàn tất: {added}/{total} poster." if total
                       else "Không còn phim nào thiếu poster.")

    return work


def plot_work(app, limit):
    """Trả về hàm work: điền mô tả (plot) Wikipedia vi→en cho phim thiếu (chạy ngầm)."""

    def work(job):
        def progress(done, total, added):
            job.total = total
            job.done_count = done
            job.added = added
            job.current = f"{done}/{total} phim" if total else ""

        with app.app_context():
            added, total, errors = collector.fetch_missing_plots(limit=limit, progress=progress)
            job.added = added
            job.errors.extend(errors)
        job.current = ""
        job.message = (f"Hoàn tất: {added}/{total} mô tả." if total
                       else "Không còn phim nào thiếu mô tả.")

    return work
