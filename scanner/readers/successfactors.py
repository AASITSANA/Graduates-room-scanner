"""SAP SuccessFactors 'Career Site Builder' reader.

feed_url is the career site's search page, for example
  https://jobs.sap.com/search/
  https://opportunities.vodafone.com/Vodacom/search/
The search page is plain HTML: rows of a.jobTitle-link with span.jobLocation and span.jobDate.
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import http
from ..models import RawJob
from ..text import html_to_text, iso_date
from ..filter import title_verdict

MAX_PAGES = 40
MAX_DETAILS = 150


def read(company: str, feed: str, south_africa_only: bool = False) -> list[RawJob]:
    base = feed.strip()
    if not base.rstrip("/").endswith("search"):
        base = urljoin(base if base.endswith("/") else base + "/", "search/")
    jobs, seen, start = [], set(), 0
    for _ in range(MAX_PAGES):
        params = {"q": "", "startrow": start}
        if south_africa_only:
            params["locationsearch"] = "South Africa"
        soup = BeautifulSoup(http.get(base, params=params).text, "lxml")
        rows = soup.select("tr.data-row") or soup.select("li.job-tile, div.job-tile")
        new = 0
        for row in rows:
            a = row.select_one("a.jobTitle-link") or row.select_one("a[href*='/job/']")
            if not a:
                continue
            url = urljoin(base, a.get("href", ""))
            if url in seen:
                continue
            seen.add(url)
            new += 1
            loc = row.select_one(".jobLocation")
            date = row.select_one(".jobDate")
            jobs.append(RawJob(
                company=company,
                title=a.get_text(" ", strip=True),
                url=url,
                location=loc.get_text(" ", strip=True) if loc else "",
                posted=iso_date(date.get_text(strip=True)) if date else None,
                source="successfactors",
            ))
        label = soup.select_one(".paginationLabel")
        total = None
        if label:
            m = re.search(r"of\s+([\d,]+)", label.get_text())
            total = int(m.group(1).replace(",", "")) if m else None
        start += len(rows) or 25
        if new == 0 or (total is not None and start >= total):
            break

    opened = 0
    for job in jobs:
        if title_verdict(job.title) == "no" or opened >= MAX_DETAILS:
            continue
        opened += 1
        try:
            page = BeautifulSoup(http.get(job.url).text, "lxml")
            body = (page.select_one("span[itemprop='description']")
                    or page.select_one(".jobdescription") or page.select_one("main"))
            job.description = html_to_text(str(body)) if body else ""
        except Exception:
            pass
    return jobs
