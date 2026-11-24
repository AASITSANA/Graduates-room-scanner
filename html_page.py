"""Catch-all reader for careers pages that are not on a known platform.

It reads the page (with a real browser if USE_BROWSER=1, for pages built with JavaScript),
keeps only links whose text looks like a graduate opportunity, then opens each one to read the ad.
Because it only keeps clearly graduate-worded links, it is precise but can miss jobs with
plain titles. Move a company to a platform reader when you find its real portal.
"""
import os
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .. import http
from ..models import RawJob
from ..text import html_to_text, find_closing_date
from ..filter import GRAD_TITLE_RE

MAX_LINKS = 25
# link shorteners and job platforms that companies legitimately send people to
OK_OTHER_HOSTS = re.compile(r"erecruit\.co|ci\.hr|simplify\.hr|pnet\.co\.za|mcidirecthire|"
                            r"myworkday|successfactors|oraclecloud|greenhouse\.io|lever\.co|"
                            r"workable\.com|smartrecruiters|tinyurl\.com|bit\.ly|forms\.gle|"
                            r"gov\.za|org\.za", re.I)
# menu labels such as 'Graduates', 'Internships', 'Early careers', 'View internships'
MENU_LABEL = re.compile(
    r"^(?:our |view |see |explore |apply for |more on |find out about )?"
    r"(?:graduates?|graduate (?:recruitment|opportunities|programmes?|careers)|internships?|"
    r"learnerships?|early[\s-]*careers?|students?(?: (?:and|&) graduates?)?|"
    r"graduates? (?:and|&) internships?|trainee programmes?|youth development programmes?|"
    r"internships? (?:and|&) learnerships?)\s*(?:\(\d+\))?\s*[↓›>»]*$",
    re.I,
)


def _root(host: str) -> str:
    parts = host.lower().split(".")
    keep = 3 if len(parts) >= 3 and parts[-2] in ("co", "org", "gov", "ac") else 2
    return ".".join(parts[-keep:])


def _page_html(url: str) -> str:
    if os.environ.get("USE_BROWSER") == "1":
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(user_agent=http.USER_AGENT)
                page.goto(url, wait_until="networkidle", timeout=45000)
                html = page.content()
                browser.close()
                return html
        except Exception:
            pass  # fall back to a plain request
    return http.get(url).text


def read(company: str, feed: str) -> list[RawJob]:
    soup = BeautifulSoup(_page_html(feed), "lxml")
    home = _root(urlparse(feed).netloc)
    seen, jobs = set(), []
    for a in soup.find_all("a", href=True):
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if not (8 <= len(text) <= 160) or not GRAD_TITLE_RE.search(text):
            continue
        if MENU_LABEL.match(text) or re.match(r"^(https?://|www\.)", text, re.I):
            continue  # a menu item or a bare web address, not a job title
        url = urljoin(feed, a["href"])
        u = urlparse(url)
        if u.scheme not in ("http", "https") or url in seen:
            continue
        if _root(u.netloc) != home and not OK_OTHER_HOSTS.search(u.netloc):
            continue  # links to unrelated websites (news sites, theme demos…)
        seen.add(url)
        jobs.append(RawJob(company=company, title=text, url=url, source="html"))
        if len(jobs) >= MAX_LINKS:
            break

    for job in jobs:
        if job.url.lower().endswith(".pdf"):
            continue
        try:
            page = BeautifulSoup(http.get(job.url).text, "lxml")
            main = page.select_one("main") or page.select_one("article") or page.body
            job.description = html_to_text(str(main))[:20000] if main else ""
            job.closing = find_closing_date(job.description)
        except Exception:
            pass
    return jobs
