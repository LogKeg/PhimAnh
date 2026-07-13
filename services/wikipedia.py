# services/wikipedia.py
"""Client Wikipedia REST: lấy tóm tắt nội dung + ảnh poster, không cần key."""
import requests

from config import USER_AGENT, WIKI_LANG, WIKIPEDIA_API, WIKIPEDIA_REST

TIMEOUT = 10
HEADERS = {"User-Agent": USER_AGENT}


def summary(title, lang=None):
    """Trả về (extract, thumbnail_url, error). extract = tóm tắt nội dung phim."""
    if not title:
        return "", "", None
    lang = lang or WIKI_LANG
    safe_title = requests.utils.quote(title.replace(" ", "_"), safe="")
    url = f"{WIKIPEDIA_REST.format(lang=lang)}/page/summary/{safe_title}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 404:
            return "", "", None
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return "", "", None
    extract = data.get("extract", "")
    thumbnail = (data.get("thumbnail") or {}).get("source", "")
    return extract, thumbnail, None


def resolve_qid(title, lang=None):
    """Tra tiêu đề bài Wikipedia → QID Wikidata (qua pageprops). Dùng khi tìm theo tên tiếng Việt."""
    lang = lang or WIKI_LANG
    try:
        resp = requests.get(
            WIKIPEDIA_API.format(lang=lang),
            params={
                "action": "query",
                "titles": title,
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "redirects": 1,
                "format": "json",
            },
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
    except (requests.RequestException, ValueError):
        return "", None
    for page in pages.values():
        qid = (page.get("pageprops") or {}).get("wikibase_item", "")
        if qid.startswith("Q"):
            return qid, None
    return "", None
