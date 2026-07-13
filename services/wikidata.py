# services/wikidata.py
"""Client Wikidata (SPARQL + wbsearchentities): nguồn cấu trúc chính, không cần key."""
import json

import requests

from config import USER_AGENT, WIKIDATA_API, WIKIDATA_SPARQL

TIMEOUT = 30
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/sparql-results+json",
}

# Thuộc tính đa giá trị: (tên bucket trong record, mã thuộc tính Wikidata)
MULTI_PROPS = (
    ("director", "P57"),
    ("genre", "P136"),
    ("actors", "P161"),
    ("country", "P495"),
    ("language", "P364"),
)


def sparql(query):
    """Chạy SPARQL. Trả về (bindings, error). Dùng strict=False để chịu ký tự điều khiển."""
    try:
        resp = requests.get(
            WIKIDATA_SPARQL,
            params={"query": query, "format": "json"},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = json.loads(resp.text, strict=False)
    except (requests.RequestException, ValueError) as exc:
        return [], f"Lỗi Wikidata SPARQL: {exc}"
    return data.get("results", {}).get("bindings", []), None


def search_entities(title, lang=None):
    """Tìm thực thể Wikidata theo tên. Trả về (list_qid, error)."""
    try:
        resp = requests.get(
            WIKIDATA_API,
            params={
                "action": "wbsearchentities",
                "search": title,
                "language": lang or "vi",
                "format": "json",
                "type": "item",
                "limit": "15",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        return [], f"Lỗi Wikidata search: {exc}"
    qids = [it["id"] for it in data.get("search", []) if str(it.get("id", "")).startswith("Q")]
    return qids, None


def films_by_qids(qids):
    """Trả về danh sách partial record cho các QID là phim (theo thứ tự qids)."""
    if not qids:
        return [], None
    values = " ".join(f"wd:{q}" for q in qids)
    subject = f"VALUES ?item {{ {values} }}\n      ?item wdt:P31 wd:Q11424 ."
    return _run_core_and_multi(subject, prefer_order=qids)


def films_of_year(year, limit=50):
    """Trả về partial record của các phim ra mắt trong 1 năm."""
    subject = (
        "{\n"
        "        SELECT DISTINCT ?item WHERE {\n"
        f"          ?item wdt:P31 wd:Q11424 ; wdt:P577 ?r .\n"
        f"          FILTER(YEAR(?r) = {int(year)})\n"
        "        }\n"
        f"        LIMIT {int(limit)}\n"
        "      }"
    )
    return _run_core_and_multi(subject)


def en_titles_for_qids(qids):
    """Batch resolve tiêu đề bài Wikipedia (en) cho các QID. Trả về ({qid: title}, error)."""
    if not qids:
        return {}, None
    values = " ".join(f"wd:{q}" for q in qids)
    query = f"""
    SELECT ?item ?enTitle WHERE {{
      VALUES ?item {{ {values} }}
      OPTIONAL {{ ?en schema:about ?item; schema:isPartOf <https://en.wikipedia.org/>;
                  schema:name ?enTitle . }}
    }}
    """
    bindings, err = sparql(query)
    if err:
        return {}, err
    out = {}
    for row in bindings:
        qid = _qid(_val(row, "item"))
        title = _val(row, "enTitle")
        if qid and title:
            out[qid] = title
    return out, None


def _run_core_and_multi(subject, prefer_order=None):
    """Truy vấn core (trường vô hướng) + multi (UNION đa giá trị), rồi gom lại."""
    core, err = sparql(_core_query(subject))
    if err:
        return [], err
    qids = [_qid(_val(row, "item")) for row in core]
    qids = [q for q in qids if q]
    multi = []
    if qids:
        multi, err = sparql(_multi_query(qids))
        if err:
            multi = []  # không chặn vì thiếu diễn viên/thể loại
    return _assemble(core, multi, prefer_order), None


def _core_query(subject):
    """Truy vấn trường vô hướng: 1 hàng/phim (tránh bùng nổ tích Đề-các)."""
    return f"""
    SELECT ?item ?itemLabel ?year ?released ?runtime ?imdb ?viTitle ?enTitle ?image WHERE {{
      {subject}
      OPTIONAL {{ ?item wdt:P577 ?released . BIND(YEAR(?released) AS ?year) }}
      OPTIONAL {{ ?item wdt:P2047 ?runtime . }}
      OPTIONAL {{ ?item wdt:P345 ?imdb . }}
      OPTIONAL {{ ?vi schema:about ?item; schema:isPartOf <https://vi.wikipedia.org/>; schema:name ?viTitle . }}
      OPTIONAL {{ ?en schema:about ?item; schema:isPartOf <https://en.wikipedia.org/>; schema:name ?enTitle . }}
      OPTIONAL {{ ?item wdt:P18 ?image . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "vi,en" . }}
    }}
    """


def _multi_query(qids):
    """Truy vấn UNION: 1 hàng/(phim, thuộc tính, giá trị) — tuyến tính, không nhân hàng."""
    values = " ".join(f"wd:{q}" for q in qids)
    unions = "\n      UNION ".join(
        f'{{ ?item wdt:{prop} ?val . BIND("{name}" AS ?prop) }}'
        for name, prop in MULTI_PROPS
    )
    return f"""
    SELECT ?item ?prop ?valLabel WHERE {{
      VALUES ?item {{ {values} }}
      {unions}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "vi,en" . }}
    }}
    """


def _assemble(core_bindings, multi_bindings, prefer_order=None):
    """Gom core + multi thành partial record, mỗi phim 1 dict."""
    records = {}
    order = []
    for row in core_bindings:
        qid = _qid(_val(row, "item"))
        if not qid or qid in records:
            continue
        records[qid] = {
            "wikidata_id": qid,
            "title": _val(row, "itemLabel"),
            "year": _val(row, "year"),
            "released": _val(row, "released"),
            "runtime": _runtime(_val(row, "runtime")),
            "imdb": _val(row, "imdb"),
            "vi_title": _val(row, "viTitle"),
            "en_title": _val(row, "enTitle"),
            "image": _resize(_val(row, "image")),
            "director": set(), "genre": set(), "actors": set(),
            "country": set(), "language": set(),
        }
        order.append(qid)
    for row in multi_bindings:
        qid = _qid(_val(row, "item"))
        prop = _val(row, "prop")
        if qid in records and prop in records[qid]:
            value = _val(row, "valLabel")
            if value:
                records[qid][prop].add(value)

    result = []
    for qid in (prefer_order or order):
        rec = records.get(qid)
        if not rec:
            continue
        for key in ("director", "genre", "actors", "country", "language"):
            rec[key] = ", ".join(sorted(rec[key]))
        result.append(rec)
    return result


def _val(row, key):
    return row.get(key, {}).get("value", "")


def _qid(uri):
    """Rút Q-number từ URI thực thể Wikidata."""
    return uri.rsplit("/", 1)[-1] if "entity/" in uri else ""


def _resize(image_uri):
    """Ép kích thước ảnh Commons về 400px để tải nhanh."""
    if not image_uri:
        return ""
    sep = "&" if "?" in image_uri else "?"
    return f"{image_uri}{sep}width=400"


def _runtime(seconds):
    """Wikidata lưu thời lượng phim bằng giây → đổi sang phút."""
    if not seconds:
        return ""
    try:
        secs = float(seconds)
    except ValueError:
        return ""
    minutes = round(secs / 60) if secs >= 1000 else round(secs)
    return f"{int(minutes)} min"
