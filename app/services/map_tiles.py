"""On-demand fallback for clients unable to reach the public map tile host."""
from collections import OrderedDict
import re
import threading
import time

import httpx
from fastapi import HTTPException

USER_AGENT = "CampusMove/2.0 (+https://github.com/fiiop/sports_platform)"
MAX_ENTRIES = 512
MAX_BYTES = 32 * 1024 * 1024
_cache = OrderedDict()
_cache_lock = threading.Lock()
_tile_locks = [threading.Lock() for _ in range(32)]
_downloads = threading.BoundedSemaphore(4)


def _ttl(headers):
    match = re.search(r"(?:^|,)\s*max-age=(\d+)", headers.get("cache-control", ""))
    age = headers.get("age", "0")
    return max(0, (int(match.group(1)) if match else 604800) -
               (int(age) if age.isdigit() else 0))


def get_tile(z, x, y, referer):
    if not (0 <= z <= 19 and 0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(404, "地图区域无效")
    key = (z, x, y)
    # Coalesce concurrent requests for the same tile. Limit memory and downloads.
    with _tile_locks[hash(key) % len(_tile_locks)]:
        with _cache_lock:
            cached = _cache.get(key)
            if cached:
                _cache.move_to_end(key)
                remaining = int(cached["expires"] - time.monotonic())
                if remaining > 0:
                    return cached["body"], remaining
        headers = {"User-Agent": USER_AGENT, "Referer": referer}
        if cached and cached["etag"]:
            headers["If-None-Match"] = cached["etag"]
        if not _downloads.acquire(timeout=2):
            raise HTTPException(503, "地图加载繁忙，请稍后重试")
        try:
            response = httpx.get(
                f"https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                headers=headers, timeout=httpx.Timeout(8, connect=4),
                follow_redirects=False,
            )
        except httpx.HTTPError:
            raise HTTPException(502, "地图服务暂时无法连接")
        finally:
            _downloads.release()
        if response.status_code == 304 and cached:
            body = cached["body"]
        elif response.status_code == 200 and response.content.startswith(b"\x89PNG\r\n\x1a\n"):
            body = response.content
        else:
            raise HTTPException(502, "地图服务暂时不可用")
        if len(body) > 1024 * 1024:
            raise HTTPException(502, "地图数据异常")
        ttl = _ttl(response.headers)
        cache_control = response.headers.get("cache-control", "").lower()
        if "no-store" in cache_control or "no-cache" in cache_control:
            ttl = 0
        entry = {"body": body, "expires": time.monotonic() + ttl,
                 "etag": response.headers.get("etag", cached["etag"] if cached else "")}
        with _cache_lock:
            _cache.pop(key, None)
            if ttl:
                _cache[key] = entry
                while len(_cache) > MAX_ENTRIES or sum(len(v["body"]) for v in _cache.values()) > MAX_BYTES:
                    _cache.popitem(last=False)
        return body, ttl
