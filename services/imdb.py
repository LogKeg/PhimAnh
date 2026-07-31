# services/imdb.py
"""IMDb poster scraper (Playwright headless Chromium).

IMDb chặn bot bằng Akamai (HTTP 202 + body rỗng với requests) → phải dùng trình
duyệt headless. Mô-đun này CHỈ lấy og:image (poster chính thức) cho phim có imdb_id.

⚠ Viển ToS IMDb — chỉ dùng cho mục đích cá nhân/nghiên cứu.
"""

# UA trình duyệt thật (UA app "PhimAnhApp" sẽ bị IMDb phát hiện là bot)
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
# Cờ che headless: IMDb (Akamai) phát hiện HeadlessChrome → trả trang stub
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
STEALTH_JS = "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"

TIMEOUT_MS = 30000


def _new_page(browser):
    """Tạo page với UA thật + che webdriver để IMDb phục vụ trang đầy đủ."""
    page = browser.new_page(
        user_agent=BROWSER_UA,
        locale="en-US",
        viewport={"width": 1280, "height": 800},
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    page.add_init_script(STEALTH_JS)
    return page


def _fetch_poster(page, imdb_id):
    """Mở trang IMDb title → đợi meta og:image xuất hiện → đọc."""
    page.goto(
        f"https://www.imdb.com/title/{imdb_id}/",
        wait_until="domcontentloaded",
        timeout=TIMEOUT_MS,
    )
    try:
        page.wait_for_selector('meta[property="og:image"]', timeout=15000)
    except Exception:  # pylint: disable=broad-except
        pass  # thử đọc dù không đợi được (tránh kẹt networkidle trên trang nặng)
    url = page.get_attribute('meta[property="og:image"]', "content")
    return (url or "").strip()


def imdb_poster(imdb_id):
    """Lấy poster IMDb cho 1 phim. Trả về (url, error). Mở/đóng trình duyệt riêng."""
    if not imdb_id:
        return "", "Thiếu imdb_id."
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "", "Chưa cài playwright (pip install playwright && playwright install chromium)."
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=LAUNCH_ARGS)
            try:
                url = _fetch_poster(_new_page(browser), imdb_id)
            finally:
                browser.close()
    except Exception as exc:  # pylint: disable=broad-except
        return "", f"Lỗi IMDb: {exc}"
    return url, (None if url else "Không tìm og:image trên trang IMDb.")


def imdb_posters_iter(items, limit=20):
    """Generator: mở 1 trình duyệt, yield (id, url, error) lần lượt cho mỗi phim.

    Giữ trình duyệt mở xuyên suốt — dùng cho tiến độ sống (callback từng phim).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        for item_id, _ in items[:limit]:
            yield (item_id, "", "chưa cài playwright")
        return
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=LAUNCH_ARGS)
            page = _new_page(browser)
            try:
                for item_id, imdb_id in items[:limit]:
                    if not imdb_id:
                        yield (item_id, "", "thiếu imdb_id")
                        continue
                    try:
                        url = _fetch_poster(page, imdb_id)
                        yield (item_id, url, None if url else "không có og:image")
                    except Exception as exc:  # pylint: disable=broad-except
                        yield (item_id, "", f"lỗi: {exc}")
            finally:
                browser.close()
    except Exception as exc:  # pylint: disable=broad-except
        # Không mở được trình duyệt → báo lỗi cho mọi item (chưa yield cái nào)
        for item_id, _ in items[:limit]:
            yield (item_id, "", f"lỗi trình duyệt: {exc}")


def imdb_posters_bulk(items, limit=20):
    """Lấy poster cho nhiều phim (mở 1 trình duyệt). Trả về list of (id, url, error)."""
    return list(imdb_posters_iter(items, limit=limit))


def _fetch_title(page, imdb_id):
    """Mở trang IMDb title → đọc meta og:title, bỏ suffix '- IMDb' và '(Năm)'."""
    import re
    page.goto(
        f"https://www.imdb.com/title/{imdb_id}/",
        wait_until="domcontentloaded",
        timeout=TIMEOUT_MS,
    )
    try:
        page.wait_for_selector('meta[property="og:title"]', timeout=15000)
    except Exception:  # pylint: disable=broad-except
        pass
    raw = (page.get_attribute('meta[property="og:title"]', "content") or "").strip()
    raw = re.sub(r"\s*-\s*IMDb\s*$", "", raw).strip()        # "Inception - IMDb" → "Inception"
    raw = re.sub(r"\s*\(\d{4}\)\s*$", "", raw).strip()        # "Inception (2010)" → "Inception"
    return raw


def imdb_titles_iter(items, limit=20):
    """Generator: mở 1 trình duyệt, yield (id, title, error) cho mỗi phim.

    Dùng cho fix_qid_titles: rescue tên phim từ IMDb og:title cho phim đang bị
    lưu title = mã QID (Wikidata không có nhãn).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        for item_id, _ in items[:limit]:
            yield (item_id, "", "chưa cài playwright")
        return
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=LAUNCH_ARGS)
            page = _new_page(browser)
            try:
                for item_id, imdb_id in items[:limit]:
                    if not imdb_id:
                        yield (item_id, "", "thiếu imdb_id")
                        continue
                    try:
                        title = _fetch_title(page, imdb_id)
                        yield (item_id, title, None if title else "không có og:title")
                    except Exception as exc:  # pylint: disable=broad-except
                        yield (item_id, "", f"lỗi: {exc}")
            finally:
                browser.close()
    except Exception as exc:  # pylint: disable=broad-except
        for item_id, _ in items[:limit]:
            yield (item_id, "", f"lỗi trình duyệt: {exc}")
