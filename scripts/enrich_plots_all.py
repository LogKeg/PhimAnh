# scripts/enrich_plots_all.py
"""Lấy mô tả phim tới khi hết: lặp lô 5000 cho đến khi không còn phim thiếu
hoặc phần còn lại không fetch được (không có bài Wikipedia).

Chạy độc lập (process riêng), ghi chung movies.db (WAL cho phép song song server):
    python3 scripts/enrich_plots_all.py
"""
import os
import sys

# Cho phép import các module ở thư mục gốc
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Phải load .env TRƯỚC khi import app/config — config._build_database_uri() chạy lúc
# import, nếu chưa có DATABASE_URL sẽ fallback SQLite (mất dữ liệu vào movies.db).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app import create_app          # noqa: E402
from services import collector      # noqa: E402

BATCH = 5000


def main():
    app = create_app()
    total_added = 0
    batch = 0
    with app.app_context():
        while True:
            batch += 1
            print(f"--- lô {batch} ---", flush=True)

            def progress(done, total, added):
                print(f"\r  {done}/{total} (+{added})", end="", flush=True)

            added, total, errors = collector.fetch_missing_plots(limit=BATCH, progress=progress)
            print()
            total_added += added
            print(f"  → +{added}/{total} mô tả (tích lũy +{total_added})", flush=True)
            if errors:
                print("  lỗi (mẫu):", errors[:2])
            if total == 0:
                print("Dừng: hết phim thiếu mô tả.")
                break
            if added == 0:
                print("Dừng: phần còn lại không có bài Wikipedia (không fetch được).")
                break
    print(f"Hoàn tất: +{total_added} mô tả.")


if __name__ == "__main__":
    main()
