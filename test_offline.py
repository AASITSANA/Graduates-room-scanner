"""Offline tests: every reader is fed sample data shaped like the real portals' responses.
Run with:  python -m pytest -q   (or: python tests/test_offline.py)
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanner import http  # noqa: E402
from scanner.models import RawJob  # noqa: E402
from scanner.filter import classify, title_verdict, min_years_required, province_of  # noqa: E402
from scanner.readers import ats_simple, workday, successfactors, oracle, html_page, dpsa  # noqa: E402
import discover  # noqa: E402

TODAY = date(2026, 11, 22)


class FakeResp:
    def __init__(self, payload=None, text="", content=b"", url=""):
        self._p, self.text, self.content, self.url = payload, text, content, url
        self.headers = {"Content-Type": "text/html"}

    def json(self):
        return self._p


def patch(get=None, post=None):
    if get:
        http.get = get
    if post:
        http.post = post


# ---------- filter ----------

def test_title_verdicts():
    assert title_verdict("Graduate Programme 2027 – Finance") == "yes"
    assert title_verdict("IT Internship (Grow-IT)") == "yes"
    assert title_verdict("Candidate Attorney 2028") == "yes"
    assert title_verdict("Senior Data Engineer") == "no"
    assert title_verdict("Graduate Programme Manager") == "no"
    assert title_verdict("Engineering Bursary 2027") == "no"
    assert title_verdict("Data Analyst") == "maybe"


def test_years():
    assert min_years_required("Minimum of 5 years' relevant experience") == 5
    assert min_years_required("0-2 years experience in a similar role") == 0
    assert min_years_required("no years mentioned") is None


def test_province():
    assert province_of("Sandton, Gauteng, South Africa") == "Gauteng"
    assert province_of("Cape Town") == "Western Cape"
    assert province_of("Johannesburg; Durban") == "Multiple"


def raw(title, loc="Johannesburg", desc="", closing=None):
    return RawJob(company="Testco", title=title, url="https://x/1", location=loc,
                  description=desc, closing=closing)


def test_classify_keeps_and_drops():
    j = classify(raw("Graduate Programme 2027 - Software Engineering",
                     desc="BSc Computer Science degree. Closing date: 30 November 2026"),
                 "Technology", True, TODAY)
    assert j and j.job_type == "Graduate programme" and "IT" in j.faculties
    assert j.closing_date == "2026-11-30" and j.province == "Gauteng"
    # expired
    assert classify(raw("Graduate Programme", closing="2026-10-01"), "x", False, TODAY) is None
    # outside SA for a multinational
    assert classify(raw("Graduate Programme", loc="London, UK"), "x", True, TODAY) is None
    # local company, unhelpful location
    assert classify(raw("Finance Intern", loc="Head Office"), "x", False, TODAY)
    # foreign location for local company
    assert classify(raw("Finance Intern", loc="Gaborone, Botswana"), "x", False, TODAY) is None
    # too much experience
    assert classify(raw("Junior Accountant", desc="Minimum 3 years experience"), "x", False, TODAY) is None
    # plain title needs proof of entry level
    assert classify(raw("Data Analyst", desc="We need an analyst."), "x", False, TODAY) is None
    k = classify(raw("Data Analyst", desc="Ideal for recent graduates with a BCom degree."), "x", False, TODAY)
    assert k and k.confidence == "check"
    # matric-only learnership
    assert classify(raw("Retail Learnership", desc="Grade 12 / Matric certificate required."),
                    "x", False, TODAY) is None
    assert classify(raw("Learnership", desc="Completed diploma or degree in Marketing."), "x", False, TODAY)


# ---------- readers ----------

def test_greenhouse():
    patch(get=lambda url, **k: FakeResp({"jobs": [{
        "title": "Graduate Software Engineer", "absolute_url": "https://job-boards.greenhouse.io/takealotcom/jobs/1",
        "location": {"name": "Cape Town"}, "content": "&lt;p&gt;Join our graduate programme&lt;/p&gt;",
        "first_published": "2026-11-01T10:00:00Z"}]}))
    jobs = ats_simple.greenhouse("Takealot", "takealotcom")
    assert jobs[0].description == "Join our graduate programme" and jobs[0].posted == "2026-11-01"


def test_lever_workable_smartrecruiters():
    patch(get=lambda url, **k: FakeResp([{"text": "Intern", "hostedUrl": "https://jobs.lever.co/a/1",
                                          "categories": {"location": "Johannesburg"}, "createdAt": 1793000000000,
                                          "descriptionPlain": "intern"}]))
    assert ats_simple.lever("A", "https://jobs.lever.co/a")[0].location == "Johannesburg"
    patch(get=lambda url, **k: FakeResp({"jobs": [{"title": "Graduate Developer", "url": "https://apply.workable.com/clickatell/j/X/",
                                                   "city": "Cape Town", "country": "South Africa",
                                                   "published_on": "2026-09-04", "description": "<b>10-month</b>"}]}))
    w = ats_simple.workable("Clickatell", "clickatell")[0]
    assert w.location == "Cape Town, South Africa" and w.description == "10-month"
    calls = []

    def sr(url, params=None, **k):
        calls.append(params["offset"])
        return FakeResp({"totalFound": 1, "content": [{"id": "9", "name": "Graduate", "releasedDate": "2026-11-01",
                                                       "location": {"city": "Midrand", "country": "za"}}]})
    patch(get=sr)
    s = ats_simple.smartrecruiters("Bosch", "Bosch")
    assert s[0].url.endswith("/Bosch/9") and calls == [0]


def test_workday():
    def post(url, json=None, **k):
        assert url == "https://absa.wd3.myworkdayjobs.com/wday/cxs/absa/ABSAcareersite/jobs"
        if json["offset"] == 0:
            return FakeResp({"total": 2, "jobPostings": [
                {"title": "Graduate Programme 2027", "externalPath": "/job/Johannesburg/Grad_R1",
                 "locationsText": "Johannesburg", "postedOn": "Posted 2 Days Ago"},
                {"title": "Senior Manager Credit", "externalPath": "/job/x/R2", "locationsText": "Sandton",
                 "postedOn": "Posted Today"}]})
        return FakeResp({"total": 0, "jobPostings": []})

    opened = []

    def get(url, **k):
        opened.append(url)
        return FakeResp({"jobPostingInfo": {"jobDescription": "<p>Closing date: 15 December 2026</p>",
                                            "startDate": "2026-11-20", "country": {"descriptor": "South Africa"},
                                            "externalUrl": "https://absa.wd3.myworkdayjobs.com/ABSAcareersite/job/Grad_R1"}})
    patch(get=get, post=post)
    jobs = workday.read("Absa", "https://absa.wd3.myworkdayjobs.com/en-US/ABSAcareersite")
    assert len(jobs) == 2 and len(opened) == 1  # senior role not opened
    assert jobs[0].location == "Johannesburg, South Africa" and jobs[0].posted == "2026-11-20"
    assert workday._parts("https://wd3.myworkdaysite.com/recruiting/sasol/Sasol") == (
        "wd3.myworkdaysite.com", "sasol", "Sasol")


SF_PAGE = """<span class="paginationLabel">Results 1 – 2 of 2</span><table>
<tr class="data-row"><td><a class="jobTitle-link" href="/Vodacom/job/Midrand-2027-Early-Careers/1/">2027 Vodacom Early Careers Programmes</a>
<span class="jobLocation">Midrand, ZA</span><span class="jobDate">29 May 2026</span></td></tr>
<tr class="data-row"><td><a class="jobTitle-link" href="/Vodacom/job/x/2/">Senior Engineer</a>
<span class="jobLocation">Midrand, ZA</span></td></tr></table>"""


def test_successfactors():
    def get(url, params=None, **k):
        if "search" in url:
            return FakeResp(text=SF_PAGE)
        return FakeResp(text='<span itemprop="description">Graduate programme for 2026 graduates</span>')
    patch(get=get)
    jobs = successfactors.read("Vodacom", "https://opportunities.vodafone.com/Vodacom/search/", True)
    assert jobs[0].url == "https://opportunities.vodafone.com/Vodacom/job/Midrand-2027-Early-Careers/1/"
    assert jobs[0].posted == "2026-05-29" and "Graduate programme" in jobs[0].description
    assert jobs[1].description == ""


def test_oracle():
    def get(url, params=None, **k):
        if url.endswith("recruitingCEJobRequisitions"):
            return FakeResp({"items": [{"TotalJobsCount": 1, "requisitionList": [
                {"Id": "123", "Title": "Graduate Development Programme 2027", "PrimaryLocation": "Pretoria, South Africa",
                 "PostedDate": "2026-04-01"}]}]})
        return FakeResp({"items": [{"ExternalDescriptionStr": "<p>One-year programme</p>",
                                    "ExternalPostedEndDate": "2026-04-30"}]})
    patch(get=get)
    j = oracle.read("SARB", "https://fa-evra-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/SARB/jobs")[0]
    assert j.url.endswith("/sites/SARB/job/123") and j.closing == "2026-04-30"


def test_html_page():
    def get(url, **k):
        if url == "https://example.co.za/careers":
            return FakeResp(text='<a href="/grad">Graduate Programme 2027 – apply now</a><a href="/about">About us</a>')
        return FakeResp(text="<main>Applications close 12 January 2027.</main>")
    patch(get=get)
    jobs = html_page.read("Example", "https://example.co.za/careers")
    assert len(jobs) == 1 and jobs[0].closing == "2027-01-12"


DPSA_TEXT = """NATIONAL TREASURY
POST 45/01 : INTERNSHIP PROGRAMME 2027/2028 REF NO: NT 1/2027
STIPEND : R8 000 per month
CENTRE : Pretoria
REQUIREMENTS : A degree in Economics
CLOSING DATE : 05 December 2026
DEPARTMENT OF HEALTH
POST 45/02 : DEPUTY DIRECTOR: FINANCE REF NO: H1
CENTRE : Pretoria
POST 45/03 : GRADUATE INTERN: COMMUNICATION REF NO: H2
CENTRE : Pretoria
CLOSING DATE : 12 December 2026"""


def test_dpsa():
    jobs = dpsa.parse_circular_text(DPSA_TEXT, "https://www.dpsa.gov.za/x.pdf")
    assert [j.title for j in jobs] == ["Internship Programme 2027/2028", "Graduate Intern: Communication"]
    assert jobs[0].company == "National Treasury" and jobs[0].closing == "2026-12-05"
    assert jobs[1].company == "Department Of Health" and jobs[1].location == "Pretoria"


def test_discover_signatures():
    d = discover.detect_in('<a href="https://absa.wd3.myworkdayjobs.com/en-US/ABSAcareersite">Jobs</a>', "p")
    assert d[0] == "workday" and d[1].endswith("/en-US/ABSAcareersite")
    assert discover.detect_in('src="https://boards.greenhouse.io/embed/job_board/js?for=takealotcom"', "p")[1] == "takealotcom"
    assert discover.detect_in('https://jobs.lever.co/yoco/abc', "p")[:2] == ("lever", "yoco")
    sf = discover.detect_in('<link href="https://rmkcdn.successfactors.com/x.css">',
                            "https://jobs.example.com/Brand/search/?q=")
    assert sf[:2] == ("successfactors", "https://jobs.example.com/Brand/search/")
    assert discover.detect_in("nothing here", "p") is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)


def test_discover_page_scoring_and_weak_rows(tmp_path=None):
    root = "pick.co.za"
    good = discover._score("https://www.pick.co.za/careers/graduates", root)
    news = discover._score("https://www.pick.co.za/news/graduates-celebrate", root)
    other = discover._score("https://www.sadc.int/vacancies", root)
    portal = discover._score("https://shoprite.erecruit.co/candidateapp/jobs/browse/", root)
    assert good > 0 and news < 0 and other < good and portal > 0
    assert discover._root("careers.capitecbank.co.za") == "capitecbank.co.za"
    # CSB must not trigger on the plain word 'careersite'
    assert discover.detect_in("visit our careersite today", "https://x.co.za/") is None


def test_discover_main_applies_fixes(tmp_path=None):
    import csv, tempfile
    d = Path(tempfile.mkdtemp())
    f = d / "companies.csv"
    fields = ["company", "sector", "employer_type", "website", "platform", "feed_url", "global", "active", "notes"]
    rows = [
        {"company": "Liberty", "website": "liberty.co.za", "platform": "smartrecruiters",
         "feed_url": "StandardBankGroup", "notes": "auto: found"},
        {"company": "Clover", "website": "clover.co.za", "platform": "successfactors",
         "feed_url": "https://www.clover.co.za/search/", "notes": "auto: career site"},
        {"company": "Absa", "website": "absa.co.za", "platform": "workday",
         "feed_url": "https://absa.wd3.myworkdayjobs.com/ABSAcareersite", "notes": "auto: found"},
        {"company": "Stanlib", "website": "stanlib.com", "platform": "html",
         "feed_url": "https://stanlib.com/cms/insights-articles/x", "notes": "auto: no known platform – check"},
    ]
    with f.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    checked = []
    old = (discover.COMPANIES, discover.REPORT, discover.discover, sys.argv)
    discover.COMPANIES, discover.REPORT = f, d / "report.md"
    discover.discover = lambda r: (checked.append(r["company"]) or (None, None, "website did not load"))
    sys.argv = ["discover.py"]
    try:
        discover.main()
    finally:
        discover.COMPANIES, discover.REPORT, discover.discover, sys.argv = old
    out = {r["company"]: r for r in csv.DictReader(f.open())}
    assert out["Liberty"]["active"] == "no"
    assert sorted(checked) == ["Clover", "Stanlib"]  # Absa is a good result, left alone
    assert out["Clover"]["platform"] == "" and out["Absa"]["platform"] == "workday"
