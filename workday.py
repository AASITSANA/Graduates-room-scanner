"""Workday reader.

feed_url is the company's Workday careers address, for example
  https://absa.wd3.myworkdayjobs.com/ABSAcareersite
Workday serves the same jobs as JSON at /wday/cxs/<tenant>/<site>/jobs.
"""
from urllib.parse import urlparse

from .. import http
from ..models import RawJob
from ..text import html_to_text, iso_date, relative_posted
from ..filter import title_verdict

PAGE = 20  # Workday's maximum page size
MAX_JOBS = 2000
MAX_DETAILS = 60  # job pages opened per company per run (Workday is paced slowly)
BIG_PORTAL = 300  # above this many jobs, search for graduate words instead of reading every job
SEARCH_WORDS = ["graduate", "intern", "trainee", "learnership", "junior", "entry level",
                "candidate", "apprentice", "early careers", "YES programme"]


def _parts(feed: str):
    u = urlparse(feed.strip())
    host = u.netloc
    segs = [s for s in u.path.split("/") if s]
    # skip a locale segment such as en-US
    segs = [s for s in segs if not (len(s) == 5 and s[2] == "-")]
    if "myworkdaysite.com" in host and len(segs) >= 3 and segs[0] == "recruiting":
        # https://wd3.myworkdaysite.com/recruiting/<tenant>/<site>
        return host, segs[1], segs[2]
    tenant = host.split(".")[0]
    site = segs[0] if segs else ""
    return host, tenant, site


def job_url(host: str, tenant: str, site: str, path: str) -> str:
    if "myworkdaysite.com" in host:
        return f"https://{host}/recruiting/{tenant}/{site}{path}"
    return f"https://{host}/{site}{path}"


def read(company: str, feed: str) -> list[RawJob]:
    host, tenant, site = _parts(feed)
    api = f"https://{host}/wday/cxs/{tenant}/{site}"

    def page(search: str, offset: int):
        return http.post(
            f"{api}/jobs",
            json={"appliedFacets": {}, "limit": PAGE, "offset": offset, "searchText": search},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        ).json()

    def collect(search: str, limit: int):
        found, offset, total = [], 0, None
        while True:
            data = page(search, offset)
            if total is None:
                total = data.get("total", 0)
            batch = data.get("jobPostings", [])
            found.extend(batch)
            offset += PAGE
            if not batch or offset >= (total or 0) or offset >= limit:
                return found, total or 0

    first, total = collect("", PAGE)  # one page tells us how big the portal is
    if total <= BIG_PORTAL:
        postings, _ = collect("", MAX_JOBS)
    else:
        postings, seen = [], set()
        for word in SEARCH_WORDS:
            hits, _ = collect(word, 200)
            for p in hits:
                if p.get("externalPath") not in seen:
                    seen.add(p.get("externalPath"))
                    postings.append(p)

    jobs, opened = [], 0
    for p in postings:
        title = p.get("title", "")
        path = p.get("externalPath", "")
        job = RawJob(
            company=company,
            title=title,
            url=job_url(host, tenant, site, path),
            location=p.get("locationsText", ""),
            posted=relative_posted(p.get("postedOn", "")),
            source="workday",
        )
        # Only open the full ad when the title could be a graduate job.
        if title_verdict(title) != "no" and opened < MAX_DETAILS and path:
            opened += 1
            try:
                info = http.get(f"{api}{path}", headers={"Accept": "application/json"}).json()
                jp = info.get("jobPostingInfo", {})
                job.description = html_to_text(jp.get("jobDescription", ""))
                job.posted = iso_date(jp.get("startDate")) or job.posted
                job.closing = iso_date(jp.get("endDate"))
                country = ((jp.get("country") or {}).get("descriptor")) or ""
                if country and country not in job.location:
                    job.location = f"{job.location}, {country}".strip(", ")
                job.url = jp.get("externalUrl") or job.url
            except Exception:
                pass  # keep the listing-level info
        jobs.append(job)
    return jobs
