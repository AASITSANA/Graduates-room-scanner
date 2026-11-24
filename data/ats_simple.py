"""Readers for hiring platforms that publish a clean public job feed.

feed_url in companies.csv holds the company's board name on that platform:
  greenhouse       -> board token,      e.g. takealotcom   (job-boards.greenhouse.io/takealotcom)
  lever            -> company name,     e.g. yoco          (jobs.lever.co/yoco)
  workable         -> account name,     e.g. clickatell    (apply.workable.com/clickatell)
  smartrecruiters  -> company id,       e.g. Bosch         (jobs.smartrecruiters.com/Bosch)
A full board URL also works; the name is taken from it.
"""
from urllib.parse import urlparse

from .. import http
from ..models import RawJob
from ..text import html_to_text, iso_date


def _board_name(feed: str) -> str:
    feed = feed.strip()
    if "://" not in feed:
        return feed.strip("/")
    parts = [p for p in urlparse(feed).path.split("/") if p]
    return parts[0] if parts else ""


def greenhouse(company: str, feed: str) -> list[RawJob]:
    token = _board_name(feed)
    data = http.get(
        f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", params={"content": "true"}
    ).json()
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(RawJob(
            company=company,
            title=j.get("title", ""),
            url=j.get("absolute_url", ""),
            location=(j.get("location") or {}).get("name", ""),
            description=html_to_text(j.get("content", "")),
            posted=iso_date(j.get("first_published") or j.get("updated_at")),
            source="greenhouse",
        ))
    return jobs


def lever(company: str, feed: str) -> list[RawJob]:
    name = _board_name(feed)
    data = http.get(f"https://api.lever.co/v0/postings/{name}", params={"mode": "json"}).json()
    jobs = []
    for j in data:
        cats = j.get("categories") or {}
        loc = cats.get("location") or ", ".join(cats.get("allLocations") or [])
        jobs.append(RawJob(
            company=company,
            title=j.get("text", ""),
            url=j.get("hostedUrl", ""),
            location=loc or "",
            description=j.get("descriptionPlain") or html_to_text(j.get("description", "")),
            posted=iso_date(j.get("createdAt")),
            source="lever",
        ))
    return jobs


def workable(company: str, feed: str) -> list[RawJob]:
    account = _board_name(feed)
    data = http.get(
        f"https://apply.workable.com/api/v1/widget/accounts/{account}", params={"details": "true"}
    ).json()
    jobs = []
    for j in data.get("jobs", []):
        loc = ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)
        jobs.append(RawJob(
            company=company,
            title=j.get("title", ""),
            url=j.get("url") or j.get("application_url", ""),
            location=loc,
            description=html_to_text(j.get("description", "")),
            posted=iso_date(j.get("published_on") or j.get("created_at")),
            source="workable",
        ))
    return jobs


def smartrecruiters(company: str, feed: str) -> list[RawJob]:
    cid = _board_name(feed)
    jobs, offset = [], 0
    while True:
        data = http.get(
            f"https://api.smartrecruiters.com/v1/companies/{cid}/postings",
            params={"limit": 100, "offset": offset, "country": "za"},
        ).json()
        items = data.get("content", [])
        for j in items:
            loc = j.get("location") or {}
            jobs.append(RawJob(
                company=company,
                title=j.get("name", ""),
                url=f"https://jobs.smartrecruiters.com/{cid}/{j.get('id')}",
                location=", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x),
                posted=iso_date(j.get("releasedDate")),
                source="smartrecruiters",
            ))
        offset += len(items)
        if not items or offset >= data.get("totalFound", 0) or offset >= 1000:
            break
    return jobs
