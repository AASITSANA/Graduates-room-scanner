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
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from scanner import http
from fixes import FIXES

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
CSB_SIGNS = re.compile(r"rmkcdn\.successfactors\.com|class=\"jobTitle-link", re.IGNORECASE)
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


_BLOCKED = threading.local()


def _fetch(url):
    try:
        r = http.get(url, allow_redirects=True)
        if "html" in r.headers.get("Content-Type", "html"):
            return r.url, r.text
    except Exception as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        if code in (401, 403, 429, 503):
            _BLOCKED.flag = True
    return None, None


BAD_PAGE = re.compile(r"/news|/article|/posts?/|/insight|/blog|/media|/press|\.pdf$|404|/error|"
                      r"military|funding|bursar|adviser|advisor|/europe/|/en[-_]us/|/us/", re.I)
GOOD_PAGE = re.compile(r"vacanc|/jobs?\b|job-search|opportunit|/careers?\b|career-opportunit", re.I)
EARLY_PAGE = re.compile(r"graduate|intern|early[-_]?career|student|youth|learnership", re.I)
JOB_HOSTS = re.compile(r"erecruit\.co|ci\.hr|simplify\.hr|pnet\.co\.za|mcidirecthire|"
                       r"trending-talent|careers24|myworkday|successfactors|oraclecloud", re.I)


def _root(host):
    parts = host.lower().split(".")
    keep = 3 if len(parts) >= 3 and parts[-2] in ("co", "org", "gov", "ac") else 2
    return ".".join(parts[-keep:])


def _score(url, site_root):
    u = urlparse(url)
    score = 0
    if GOOD_PAGE.search(u.path) or u.netloc.split(".")[0] in ("careers", "jobs", "career"):
        score += 3
    if EARLY_PAGE.search(u.path):
        score += 2
    if BAD_PAGE.search(url):
        score -= 6
    if _root(u.netloc) == site_root:
        score += 2
    elif JOB_HOSTS.search(u.netloc):
        score += 2
    else:
        score -= 3
    return score


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
    _BLOCKED.flag = False
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
        if getattr(_BLOCKED, "flag", False):
            _BLOCKED.flag = False
            return None, None, "website blocks automated visitors – add its job portal by hand"
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
        links.sort(key=lambda h: _score(h, _root(urlparse(base).netloc)), reverse=True)
        careers_pages.extend(links[4:12])
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

    site_root = _root(urlparse(base).netloc)
    ranked = sorted(set(careers_pages), key=lambda c: _score(c, site_root), reverse=True)
    if ranked and _score(ranked[0], site_root) > 0:
        return "html", ranked[0], "no known platform – generic careers page, check it"
    return None, None, "no suitable careers page found"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--only")
    args = ap.parse_args()

    with COMPANIES.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    # 1) hand-checked fixes always win (unless a row is marked 'manual')
    for r in rows:
        fix = FIXES.get(r["company"])
        if fix and not (r.get("notes") or "").lower().startswith("manual"):
            r.update(fix)

    # 2) which companies to (re)check: empty ones, plus weak automatic guesses
    def weak(r):
        notes = (r.get("notes") or "").lower()
        if notes.startswith(("manual", "fix:", "seeded")):
            return False
        platform = (r.get("platform") or "").strip()
        if not platform:
            return True
        if platform == "html" and "no known platform" in notes:
            return True
        if platform == "successfactors" and urlparse(r.get("feed_url", "")).netloc.startswith("www."):
            return True  # a company's main website is rarely its job portal
        return False

    todo = [r for r in rows
            if (r.get("active") or "yes").lower() != "no"
            and (args.redo or weak(r))
            and (not args.only or args.only.lower() in r["company"].lower())]
    print(f"Checking {len(todo)} companies…")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(discover, todo))

    lines = ["# Platform discovery", "",
             f"Checked {len(todo)} companies this run. Hand fixes from fixes.py: {len(FIXES)}.", "",
             "| Company | Platform | Feed | Note |", "|---|---|---|---|"]
    for row, (platform, feed, note) in zip(todo, results):
        if platform:
            row["platform"], row["feed_url"] = platform, feed
            row["notes"] = f"auto: {note}"
        else:
            row["platform"], row["feed_url"] = "", ""
            row["notes"] = f"auto: {note} – fill in by hand"
        lines.append(f"| {row['company']} | {platform or '—'} | {feed or '—'} | {note} |")
        print(f"{row['company']:<45} {platform or '-':<16} {feed or note}")

    with COMPANIES.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        if (r.get("active") or "yes").lower() == "no":
            key = "paused / covered elsewhere"
        else:
            key = (r.get("platform") or "").strip() or "NOT FOUND – needs a hand fix"
        counts[key] = counts.get(key, 0) + 1
    lines += ["", "## All companies by platform", ""]
    lines += [f"- {k}: {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
