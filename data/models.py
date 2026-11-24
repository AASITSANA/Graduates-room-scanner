"""The shape every reader returns, and the shape published to the website."""
from dataclasses import dataclass, field, asdict
from typing import Optional
import hashlib


@dataclass
class RawJob:
    """A job exactly as a company's portal lists it, before filtering."""
    company: str
    title: str
    url: str
    location: str = ""
    description: str = ""  # plain text, may be empty if the portal only gives a list
    posted: Optional[str] = None  # ISO date (YYYY-MM-DD) if known
    closing: Optional[str] = None  # ISO date if the portal gives one
    source: str = ""  # which reader found it

    @property
    def id(self) -> str:
        key = f"{self.company}|{self.url or self.title}".lower()
        return hashlib.sha1(key.encode()).hexdigest()[:16]


@dataclass
class Job:
    """A job that passed the graduate filter: this is what the website shows."""
    id: str
    title: str
    company: str
    sector: str
    location: str
    province: str
    job_type: str  # Graduate programme / Internship / Learnership / Trainee / Entry-level
    faculties: list[str] = field(default_factory=list)
    closing_date: Optional[str] = None
    posted_date: Optional[str] = None
    url: str = ""
    first_seen: str = ""
    last_seen: str = ""
    confidence: str = "high"  # high = clear graduate wording, check = worth a human look

    def to_dict(self) -> dict:
        return asdict(self)
