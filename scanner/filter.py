"""Decides which jobs belong on The Graduates Room and tags them.

Precision first: a job is only kept when there is clear evidence it is for graduates
(graduate wording in the title, or 0–2 years' experience in the ad) and it is in South Africa.
"""
import re
from datetime import date
from typing import Optional

from .models import RawJob, Job
from .text import find_closing_date

GRAD_TITLE_RE = re.compile(
    r"\bgrad(?:uate)?s?\b|\bintern(?:ship)?s?\b|\btrainee|\blearnership|candidate\s+attorney|"
    r"\barticle[sd]?\s+clerk|\bentry[\s-]*level|\bjunior\b|\bjnr\b|early[\s-]*careers?|"
    r"young\s+professional|\bcadet|\bapprentice|graduate\s+programme|\byes\s+(?:programme|youth)|"
    r"work[\s-]*integrated\s+learning|\bwil\b|development\s+programme",
    re.IGNORECASE,
)
SENIOR_RE = re.compile(
    r"\bsenior\b|\bsnr\b|\bsr\.?\s|\bmanager\b|\bhead\s+of\b|\bdirector\b|\bprincipal\b|"
    r"\blead\b|\bchief\b|\bexecutive\b|\bspecialist\b|\bexpert\b|\barchitect\b|\bpartner\b|"
    r"\bexperienced\b|\bsupervisor\b|\bgm\b|\bcfo\b|\bcto\b|\bvp\b",
    re.IGNORECASE,
)
STUDENT_RE = re.compile(
    r"bursar|vacation\s+work|vac\s+work|winter\s+school|scholarship|job\s+shadow|"
    r"high\s+school|grade\s+1[0-2]",
    re.IGNORECASE,
)
NO_EXPERIENCE_RE = re.compile(
    r"recent\s+graduates?|newly\s+qualified|no\s+(?:prior\s+|previous\s+)?(?:work\s+)?experience\s+"
    r"(?:is\s+)?(?:required|necessary|needed)|unemployed\s+graduates?|completed\s+(?:a\s+|your\s+)?"
    r"(?:degree|diploma)\s+(?:in|by)\s+20\d\d|0\s*[-–to]+\s*[12]\s*years?",
    re.IGNORECASE,
)
YEARS_RE = re.compile(
    r"(?:minimum\s+(?:of\s+)?|at\s+least\s+)?(\d{1,2})\s*\+?\s*(?:[-–]|to)?\s*(\d{1,2})?\s*\+?\s*"
    r"years?['’]?\s+(?:of\s+)?(?:relevant\s+|proven\s+|working\s+|work\s+|practical\s+|related\s+)*"
    r"experience",
    re.IGNORECASE,
)
DEGREE_RE = re.compile(r"degree|diploma|bachelor|\bb\.?\s?(?:com|sc|a|tech|eng)\b|nqf\s*(?:level\s*)?[5-8]|"
                       r"graduate|honours|llb", re.IGNORECASE)

SA_RE = re.compile(r"south\s+africa|\bZA\b|\bZAF\b|\bRSA\b|\bSA\b", re.IGNORECASE)

PROVINCES = {
    "Gauteng": ["gauteng", "johannesburg", "joburg", "jhb", "sandton", "midrand", "pretoria", "tshwane",
                "centurion", "rosslyn", "randburg", "roodepoort", "soweto", "ekurhuleni", "kempton park",
                "edenvale", "boksburg", "germiston", "benoni", "vanderbijlpark", "woodmead", "bryanston",
                "rosebank", "braamfontein", "parktown", "bedfordview", "krugersdorp", "fourways",
                "sunninghill", "waterfall", "isando", "or tambo", "alberton", "springs"],
    "Western Cape": ["western cape", "cape town", "stellenbosch", "bellville", "paarl", "brackenfell",
                     "parow", "george", "milnerton", "claremont", "durbanville", "century city",
                     "tygerfalls", "tyger valley", "somerset west", "worcester"],
    "KwaZulu-Natal": ["kwazulu", "kzn", "durban", "pietermaritzburg", "umhlanga", "richards bay",
                      "pinetown", "ballito", "ethekwini", "westville", "newcastle"],
    "Eastern Cape": ["eastern cape", "east london", "gqeberha", "port elizabeth", "kariega",
                     "uitenhage", "mthatha", "makhanda", "bhisho"],
    "Free State": ["free state", "bloemfontein", "sasolburg", "welkom", "bethlehem"],
    "Limpopo": ["limpopo", "polokwane", "lephalale", "burgersfort", "tzaneen", "thohoyandou"],
    "Mpumalanga": ["mpumalanga", "nelspruit", "mbombela", "secunda", "witbank", "emalahleni",
                   "middelburg", "ermelo"],
    "North West": ["north west", "rustenburg", "mahikeng", "mafikeng", "potchefstroom", "brits",
                   "klerksdorp"],
    "Northern Cape": ["northern cape", "kimberley", "upington", "kathu", "kuruman", "springbok"],
}

FACULTIES = {
    "Commerce": ["accounting", "accountant", "finance", "financial", "audit", "tax", "economics",
                 "business", "commerce", "bcom", "marketing", "sales", "supply chain", "logistics",
                 "procurement", "actuarial", "investment", "banking", "risk", "human resources",
                 "hr ", "management", "analyst"],
    "Engineering": ["engineer", "engineering", "mechanical", "electrical", "chemical", "civil",
                    "industrial", "mining engineer", "metallurg", "mechatronic", "beng", "bsc eng"],
    "IT": ["software", "developer", "programmer", "data ", "data scientist", "data analyst", "it ",
           "information technology", "computer science", "cyber", "cloud", "devops", "tech ",
           "technology", "systems", "network", "ai ", "machine learning"],
    "Law": ["law", "legal", "llb", "attorney", "compliance", "paralegal"],
    "Science": ["science", "bsc", "chemist", "chemistry", "biology", "physics", "mathematic",
                "statistic", "geolog", "environmental", "laborator", "agricult", "food science"],
    "Humanities": ["humanities", "communication", "journalism", "public relations", "media",
                   "political", "public administration", "governance", "social", "psychology",
                   "international relations", "development studies", "policy", "administration"],
    "Health": ["nurs", "pharmac", "medical", "health", "clinical", "physiotherap", "radiograph",
               "dietitian", "occupational therap"],
    "Built Environment": ["architect", "quantity survey", "construction", "town planning",
                          "property", "real estate", "built environment", "surveying"],
}


def title_verdict(title: str) -> str:
    """'yes' = graduate wording, 'no' = senior/student role, 'maybe' = needs the ad text."""
    t = title or ""
    grad = bool(GRAD_TITLE_RE.search(t))
    if STUDENT_RE.search(t):
        return "no"
    if SENIOR_RE.search(t) and not grad:
        return "no"
    if SENIOR_RE.search(t) and grad and re.search(r"\bsenior\b|\bmanager\b|\bhead\b", t, re.I):
        return "no"  # e.g. 'Graduate Programme Manager'
    return "yes" if grad else "maybe"


def min_years_required(text: str) -> Optional[int]:
    years = [int(m.group(1)) for m in YEARS_RE.finditer(text or "")]
    return min(years) if years else None


def province_of(location: str) -> str:
    loc = (location or "").lower()
    found = [p for p, words in PROVINCES.items() if any(w in loc for w in words)]
    if len(found) == 1:
        return found[0]
    return "Multiple" if found else ""


FOREIGN_RE = re.compile(
    r"botswana|namibia|zambia|zimbabwe|kenya|nigeria|ghana|mauritius|mozambique|eswatini|lesotho|"
    r"tanzania|uganda|malawi|angola|egypt|morocco|united kingdom|\buk\b|london|ireland|india|"
    r"united states|\busa\b|canada|australia|germany|netherlands|dubai|uae|portugal|poland|"
    r"singapore|philippines|europe|emea|apac|americas",
    re.IGNORECASE,
)


def in_south_africa(raw: RawJob, is_global: bool) -> bool:
    loc = raw.location or ""
    if loc:
        if SA_RE.search(loc) or province_of(loc):
            return True
        if is_global:
            return False  # multinational: needs a South African place named
        return not FOREIGN_RE.search(loc)  # local company, e.g. 'Head Office'
    if not is_global:
        return True  # South African company with no location listed
    return bool(SA_RE.search(raw.description[:3000]) or province_of(raw.description[:3000]))


def job_type_of(title: str, description: str) -> str:
    t = title.lower()
    if "learnership" in t:
        return "Learnership"
    if re.search(r"intern", t):
        return "Internship"
    if re.search(r"trainee|candidate attorney|article|cadet|apprentice", t):
        return "Trainee"
    if re.search(r"grad|programme|program|young professional|early career", t):
        return "Graduate programme"
    return "Entry-level"


def faculties_of(title: str, description: str) -> list[str]:
    text = f" {title} {title} {description[:4000]} ".lower()
    scores = {}
    for fac, words in FACULTIES.items():
        n = sum(text.count(w) for w in words)
        if n:
            scores[fac] = n
    if not scores or re.search(r"any\s+(?:degree|discipline|field)|all\s+(?:degrees|faculties|fields)",
                               text):
        return ["All faculties"]
    ranked = sorted(scores, key=scores.get, reverse=True)
    top = scores[ranked[0]]
    return [f for f in ranked if scores[f] >= max(2, top * 0.4)][:3] or ranked[:1]


def classify(raw: RawJob, sector: str, is_global: bool, today: date | None = None) -> Optional[Job]:
    """Return a Job if it belongs on the site, otherwise None."""
    today = today or date.today()
    if not raw.title or not raw.url:
        return None
    if not in_south_africa(raw, is_global):
        return None

    verdict = title_verdict(raw.title)
    if verdict == "no":
        return None

    desc = raw.description or ""
    years = min_years_required(desc)
    if years is not None and years >= 3:
        return None

    confidence = "high"
    if verdict == "maybe":
        # plain title (e.g. 'Data Analyst'): keep only with written proof it is entry-level
        if NO_EXPERIENCE_RE.search(desc) or (years is not None and years <= 1):
            confidence = "check"
        else:
            return None

    if STUDENT_RE.search(desc[:600]) and not DEGREE_RE.search(desc):
        return None
    # learnerships for matriculants only are not graduate jobs
    if "learnership" in raw.title.lower() and desc and not DEGREE_RE.search(desc):
        return None

    closing = raw.closing or find_closing_date(desc)
    if closing and closing < today.isoformat():
        return None

    return Job(
        id=raw.id,
        title=raw.title.strip(),
        company=raw.company,
        sector=sector,
        location=raw.location.strip(),
        province=province_of(raw.location),
        job_type=job_type_of(raw.title, desc),
        faculties=faculties_of(raw.title, desc),
        closing_date=closing,
        posted_date=raw.posted,
        url=raw.url,
        confidence=confidence,
    )
