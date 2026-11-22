"""Finds which hiring platform each company uses and fills in companies.csv.

It visits the company's website and careers pages, looks for the tell-tale addresses of
Workday, SuccessFactors, Greenhouse, Lever, Workable, SmartRecruiters and Oracle, and writes
the platform and feed address into companies.csv. Companies with no known platform get the
best careers page it found, read by the catch-all 'html' reader.

Usage:
  python discover.py              # only companies with an empty platform column
  python discover.py --redo       # check every company again
  python discover.py --only Absa  # one company
Results are also listed in data/discover_report.md.
"""
import argparse
import csv
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from scanner import http

ROOT = Path(__file__).parent
COMPANIES = ROOT / "companies.csv"
REPORT = ROOT / "data" / "discover_report.md"

SIGNATURES = [
    ("workday", re.compile(r"https://[\w-]+\.wd\d+\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?[\w-]+")),
    ("workday", re.compile(r"https://wd\d+\.myworkdaysite\.com/(?:[a-z]{2}-[A-Z]{2}/)?recruiting/[\w-]+/[\w-]+")),
    ("oracle", re.compile(r"https://[\w.-]+\.oraclecloud\.com/hcmUI/CandidateExperience/[a-z]{2}/sites/[\w-]+")),
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([\w-]+)")),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([\w-]+)")),
    ("workable", re.compile(r"apply\.workable\.com/([\w-]+)")),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]+)")),
]
CSB_SIGNS = re.compile(r"rmkcdn\.successfactors\.com|jobTitle-link|careersite|csb-", re.IGNORECASE)
LEGACY_SF = re.compile(r"https://career\d*\.(?:sapsf|successfactors)\.(?:com|eu)/career\?company=[\w]+")
OTHER_ATS = {
    "PageUp": re.compile(r"pageuppeople\.com", re.I),
    "Taleo": re.compile(r"taleo\.net", re.I),
    "iCIMS": re.compile(r"icims\.com", re.I),
    "Jobvite": re.compile(r"jobvite\.com", re.I),
    "BambooHR": re.compile(r"bamboohr\.com", re.I),
    "Zoho Recruit": re.compile(r"zohorecruit", re.I),
    "Avature": re.compile(r"avature\.net", re.I),
    "Teamtailor": re.compile(r"teamtailor\.com", re.I),
}
CAREER_LINK = re.compile(r"career|vacanc|jobs?\b|join[\s-]?us|work[\s-]with[\s-]us|graduate|"
                         r"opportunit|recruit|internship", re.I)
GUESS_PATHS = ["/careers", "/careers/", "/en/careers", "/about-us/careers", "/vacancies", "/jobs"]
MAX_PAGES = 6


def _fetch(url):
    try:
        r = http.get(url, allow_redirects=True)
        if "html" in r.headers.get("Content-Type", "html"):
            return r.url, r.text
    except Exception:
        pass
    return None, None


def _clean_feed(platform, match):
    if platform in ("workday", "oracle"):
        return match.group(0)
    return match.group(1)


def detect_in(html, page_url):
    for platform, rx in SIGNATURES:
        m = rx.search(html)
        if m:
            feed = _clean_feed(platform, m)
            if platform == "greenhouse" and feed in ("embed", "v1"):
                continue
            return platform, feed, f"found on {page_url}"
    if CSB_SIGNS.search(html):
        u = urlparse(page_url)
        prefix = ""
        m = re.search(r"^(/[\w-]+)?/(?:search|job)/", u.path)
        if m and m.group(1):
            prefix = m.group(1)
        return "successfactors", f"{u.scheme}://{u.netloc}{prefix}/search/", f"career site at {page_url}"
    m = LEGACY_SF.search(html)
    if m:
        return "html", m.group(0), "old SuccessFactors site – set USE_BROWSER=1; find newer portal if any"
    for name, rx in OTHER_ATS.items():
        if rx.search(html):
            return "html", page_url, f"uses {name} (no dedicated reader yet)"
    return None


def discover(row):
    site = (row.get("website") or "").strip()
    if not site:
        return None, None, "no website"
    starts = [f"https://{site}"] if site.startswith("www.") or "/" in site else \
        [f"https://www.{site}", f"https://{site}"]
    visited, queue, careers_pages = set(), [], []
    for s in starts:
        final, html = _fetch(s)
        if html:
            queue.append((final, html))
            break
    if not queue:
        return None, None, "website did not load"
    base = queue[0][0]

    pages_done = 0
    while queue and pages_done < MAX_PAGES:
        url, html = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        pages_done += 1
        found = detect_in(html, url)
        if found:
            return found
        soup = BeautifulSoup(html, "lxml")
        # iframes often hold the real job board
        for fr in soup.find_all("iframe", src=True):
            src = urljoin(url, fr["src"])
            if src not in visited:
                f_url, f_html = _fetch(src)
                if f_html:
                    found = detect_in(f_html, f_url)
                    if found:
                        return found
        links = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            href = urljoin(url, a["href"])
            if CAREER_LINK.search(text) or CAREER_LINK.search(urlparse(href).path):
                if href.startswith("http") and href not in visited:
                    # a link straight to a known platform answers the question
                    found = detect_in(href, url)
                    if found:
                        return found
                    links.append(href)
        for href in links[:4]:
            careers_pages.append(href)
            f_url, f_html = _fetch(href)
            if f_html:
                queue.append((f_url, f_html))
        if pages_done == 1 and not links:
            for p in GUESS_PATHS:
                f_url, f_html = _fetch(urljoin(base, p))
                if f_html:
                    careers_pages.append(f_url)
                    queue.append((f_url, f_html))
                    break

    if careers_pages:
        best = next((c for c in careers_pages if re.search(r"graduate|career|vacanc", c, re.I)),
                    careers_pages[0])
        return "html", best, "no known platform – generic careers page, check it"
    return None, None, "no careers page found"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--only")
    args = ap.parse_args()

    with COMPANIES.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    todo = [r for r in rows
            if (args.redo or not (r.get("platform") or "").strip())
            and (not args.only or args.only.lower() in r["company"].lower())]
    print(f"Checking {len(todo)} companies…")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(discover, todo))

    lines = ["# Platform discovery", "", "| Company | Platform | Feed | Note |", "|---|---|---|---|"]
    for row, (platform, feed, note) in zip(todo, results):
        if platform:
            row["platform"], row["feed_url"] = platform, feed
            row["notes"] = f"auto: {note}"
        else:
            row["notes"] = f"auto: {note} – fill in by hand"
        lines.append(f"| {row['company']} | {platform or '—'} | {feed or '—'} | {note} |")
        print(f"{row['company']:<45} {platform or '-':<16} {feed or note}")

    with COMPANIES.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
