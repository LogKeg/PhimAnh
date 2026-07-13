# services/poster_cache.py
"""Cache/upload poster theo backend (env POSTER_BACKEND):
- local (mặc định): tải về static/posters/
- r2: upload lên Cloudflare R2 (S3-compatible), trả URL R2
- remote: giữ nguyên URL gốc (không cache)
"""
import os
from urllib.parse import urlparse

import requests

from config import (
    BASE_DIR, POSTER_BACKEND,
    R2_ACCESS_KEY, R2_ACCOUNT_ID, R2_BUCKET, R2_PUBLIC_BASE, R2_SECRET_KEY,
)

POSTER_DIR = os.path.join(BASE_DIR, "static", "posters")
WEB_PREFIX = "/static/posters"
TIMEOUT = 15
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    )
}


def cache_poster(remote_url, key):
    """Trả về URL lưu vào DB theo backend đang chọn."""
    if not remote_url:
        return ""
    if POSTER_BACKEND == "remote":
        return remote_url
    if POSTER_BACKEND == "r2":
        return _upload_r2(remote_url, key)
    return _cache_local(remote_url, key)


def _download(remote_url):
    """Tải ảnh, trả (bytes, content-type). Raise RequestException nếu lỗi."""
    resp = requests.get(remote_url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.content, resp.headers.get("content-type", "")


def _cache_local(remote_url, key):
    """Tải về static/posters/ — fallback URL gốc nếu lỗi."""
    if remote_url.startswith(WEB_PREFIX):
        return remote_url
    os.makedirs(POSTER_DIR, exist_ok=True)
    try:
        data, ctype = _download(remote_url)
    except requests.RequestException:
        return remote_url
    if not data or "image" not in ctype:
        return remote_url
    fname = f"{_safe(key)}{_ext(remote_url)}"
    with open(os.path.join(POSTER_DIR, fname), "wb") as fh:
        fh.write(data)
    return f"{WEB_PREFIX}/{fname}"


def _upload_r2(remote_url, key):
    """Tải rồi upload lên R2, trả public URL — fallback URL gốc nếu lỗi/chưa cấu hình."""
    if not (R2_ACCOUNT_ID and R2_BUCKET and R2_ACCESS_KEY and R2_SECRET_KEY):
        return remote_url  # R2 chưa cấu hình → giữ URL gốc
    try:
        data, ctype = _download(remote_url)
        import boto3  # lazy: local mặc định không cần boto3
        endpoint = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        s3 = boto3.client("s3", endpoint_url=endpoint,
                          aws_access_key_id=R2_ACCESS_KEY, aws_secret_access_key=R2_SECRET_KEY)
        fname = f"{_safe(key)}{_ext(remote_url)}"
        s3.put_object(Bucket=R2_BUCKET, Key=fname, Body=data,
                      ContentType=ctype or "image/jpeg")
        base = (R2_PUBLIC_BASE or "").rstrip("/")
        return f"{base}/{fname}" if base else remote_url
    except Exception:  # pylint: disable=broad-except
        return remote_url


def _ext(url):
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if ext in path:
            return ext
    return ".jpg"


def _safe(key):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (key or "x"))[:64]
