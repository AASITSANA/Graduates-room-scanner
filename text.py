"""Small text helpers shared by readers and the filter."""
import html
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from bs4 import BeautifulSoup
from dateutil import parser as dateparser


def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    raw = html.unescape(raw)  # Greenhouse sends escaped HTML
    text = BeautifulSoup(raw, "lxml").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def iso_date(value) -> Optional[str]:
    """Turn a timestamp, epoch-ms number or date string into YYYY-MM-DD."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            secs = value / 1000 if value > 10**11 else value
            return datetime.fromtimestamp(secs, tz=timezone.utc).date().isoformat()
        s = str(value).strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):  # ISO dates: never read the month as a day
            return dateparser.isoparse(s).date().isoformat()
        return dateparser.parse(s, dayfirst=True, fuzzy=True).date().isoformat()
    except (ValueError, OverflowError, TypeError):
        return None


def relative_posted(text: str, today=None) -> Optional[str]:
    """Workday says 'Posted Today', 'Posted Yesterday', 'Posted 3 Days Ago', 'Posted 30+ Days Ago'."""
    if not text:
        return None
    today = today or datetime.now(timezone.utc).date()
    t = text.lower()
    if "today" in t:
        return today.isoformat()
    if "yesterday" in t:
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\+?\s*day", t)
    if m:
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    return None


CLOSING_RE = re.compile(
    r"(?:closing|close|deadline|applications?\s+close[sd]?|apply\s+by|closing\s+date)"
    r"[^0-9A-Za-z]{0,20}(?:date)?[^0-9A-Za-z]{0,10}"
    r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9},?\s+\d{4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
    r"|\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})",
    re.IGNORECASE,
)


def find_closing_date(text: str) -> Optional[str]:
    if not text:
        return None
    m = CLOSING_RE.search(text)
    if not m:
        return None
    return iso_date(m.group(1))
