"""DPSA Public Service Vacancy Circular reader.

feed_url is the DPSA page that lists the circulars (default below). The reader downloads the
newest circular PDFs, splits them into posts ('POST 45/12 : TITLE ...') and keeps internships,
graduate and entry-level posts. Each job is credited to the department named above it.
"""
import io
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pypdf import PdfReader

from .. import http
from ..models import RawJob
from ..text import iso_date

DEFAULT_PAGE = "https://www.dpsa.gov.za/newsroom/psvc/"
MAX_PDFS = 3  # newest circular documents to read each run

POST_RE = re.compile(r"\bPOST\s+\d{1,3}\s*/\s*\d{1,4}\s*:", re.IGNORECASE)
# A department heading is a line in capitals with no colon or digits, e.g.
# 'NATIONAL TREASURY', 'DEPARTMENT OF HEALTH', 'PROVINCIAL ADMINISTRATION: GAUTENG'
DEPT_RE = re.compile(
    r"^\s*((?:PROVINCIAL ADMINISTRATION:\s*)?[A-Z][A-Z,&'\-]*(?:\s+[A-Z,&'\-()]+){1,9})\s*$"
)
NOT_DEPT = re.compile(r"^\s*(ANNEXURE|OTHER POSTS|MANAGEMENT ECHELON|AMENDMENTS?|ERRATUM|NOTE|"
                      r"APPLICATIONS|ENQUIRIES|FOR ATTENTION|CLOSING DATE)\b")
ENTRY_RE = re.compile(r"intern|graduate|trainee|learnership|entry[\s-]*level|cadet|"
                      r"young professional", re.IGNORECASE)


def _pdf_links(page_url: str) -> list[str]:
    soup = BeautifulSoup(http.get(page_url).text, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"])
        if href.lower().endswith(".pdf") and href not in links:
            links.append(href)
    return links


def _field(block: str, name: str) -> str:
    m = re.search(name + r"\s*:\s*(.+?)(?=\s+[A-Z][A-Z ]{3,}\s*:|$)", block, re.DOTALL)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:200] if m else ""


def parse_circular_text(text: str, pdf_url: str) -> list[RawJob]:
    jobs = []
    dept = "Public Service"
    lines = text.splitlines()
    # walk line by line so we know which department each post sits under
    buf, current_dept, chunks = [], dept, []
    for line in lines:
        dm = DEPT_RE.match(line)
        if dm and not NOT_DEPT.match(line) and not POST_RE.search(line):
            current_dept = dm.group(1).title()
        if POST_RE.search(line) and buf:
            chunks.append((buf_dept, "\n".join(buf)))
            buf = []
        if POST_RE.search(line) or buf:
            if not buf:
                buf_dept = current_dept
            buf.append(line)
    if buf:
        chunks.append((buf_dept, "\n".join(buf)))

    closing_all = None
    m = re.search(r"CLOSING DATE\s*:\s*([0-9]{1,2}\s+[A-Za-z]+\s+\d{4})", text)
    if m:
        closing_all = iso_date(m.group(1))

    for d, block in chunks:
        head = POST_RE.split(block, maxsplit=1)[-1]
        title = re.split(r"\s{2,}|\n|REF(?:ERENCE)?\s*NO", head, maxsplit=1)[0].strip(" :-")
        if not ENTRY_RE.search(title):
            continue
        closing = _field(block, "CLOSING DATE")
        jobs.append(RawJob(
            company=d,
            title=title.title()[:150],
            url=pdf_url,
            location=_field(block, "CENTRE"),
            description=re.sub(r"\s+", " ", block)[:6000],
            closing=iso_date(closing) if closing else closing_all,
            source="dpsa",
        ))
    return jobs


def read(company: str, feed: str) -> list[RawJob]:
    page = feed.strip() or DEFAULT_PAGE
    jobs = []
    for pdf in _pdf_links(page)[:MAX_PDFS]:
        reader = PdfReader(io.BytesIO(http.get(pdf).content))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        jobs.extend(parse_circular_text(text, pdf))
    return jobs
