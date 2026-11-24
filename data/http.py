"""Shared, polite HTTP client used by every reader."""
import time
import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = (
    "Mozilla/5.0 (compatible; GraduatesRoomSA-JobScanner/1.0; "
    "+mailto:graduatesroomsa@gmail.com)"
)
TIMEOUT = 25  # seconds per request
MIN_GAP_PER_HOST = 1.0  # seconds between two requests to the same website
# Some platforms count every company's portal as one visitor, so pace them together and slower
SHARED_HOSTS = {"myworkdayjobs.com": 3.0, "myworkdaysite.com": 3.0}

_lock = threading.Lock()
_last_hit: dict[str, float] = {}


def _wait_for_host(url: str) -> None:
    host = requests.utils.urlparse(url).netloc
    gap = MIN_GAP_PER_HOST
    for shared, shared_gap in SHARED_HOSTS.items():
        if host.endswith(shared):
            host, gap = shared, shared_gap
    with _lock:
        now = time.time()
        wait = _last_hit.get(host, 0) + gap - now
        _last_hit[host] = max(now, _last_hit.get(host, 0) + gap)
    if wait > 0:
        time.sleep(wait)


def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=4,  # waits 4, 8, 16, 32 s; a 'Retry-After' from the site is honoured
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-ZA,en;q=0.9"})
    return s


SESSION = make_session()


def get(url: str, **kw) -> requests.Response:
    _wait_for_host(url)
    r = SESSION.get(url, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def post(url: str, **kw) -> requests.Response:
    _wait_for_host(url)
    r = SESSION.post(url, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r
