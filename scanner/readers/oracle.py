"""Oracle Recruiting Cloud (Candidate Experience) reader.

feed_url is the careers address, for example
  https://fa-evra-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/SARB/jobs
The site code is the part after /sites/. If the scan finds nothing, the real code may differ
(often CX_1): open the careers page, copy the code from the address bar, and put the full URL in
companies.csv.
"""
import re
from urllib.parse import urlparse

from .. import http
from ..models import RawJob
from ..text import html_to_text, iso_date
from ..filter import title_verdict

PAGE = 25
MAX_DETAILS = 100


def read(company: str, feed: str) -> list[RawJob]:
    u = urlparse(feed.strip())
    host = u.netloc
    m = re.search(r"/sites/([^/]+)", u.path)
    site = m.group(1) if m else "CX_1"
    api = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    jobs, offset = [], 0
    while True:
        finder = (f"findReqs;siteNumber={site},facetsList=LOCATIONS,"
                  f"limit={PAGE},offset={offset},sortBy=POSTING_DATES_DESC")
        data = http.get(api, params={"onlyData": "true", "expand": "requisitionList", "finder": finder}).json()
        items = data.get("items") or [{}]
        reqs = items[0].get("requisitionList", [])
        for r in reqs:
            jobs.append(RawJob(
                company=company,
                title=r.get("Title", ""),
                url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{r.get('Id')}",
                location=r.get("PrimaryLocation", ""),
                description=html_to_text(r.get("ShortDescriptionStr", "")),
                posted=iso_date(r.get("PostedDate")),
                closing=iso_date(r.get("PostingEndDate")),
                source="oracle",
            ))
        offset += PAGE
        total = items[0].get("TotalJobsCount", 0)
        if not reqs or offset >= total or offset >= 1000:
            break

    detail_api = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
    opened = 0
    for job in jobs:
        if title_verdict(job.title) == "no" or opened >= MAX_DETAILS:
            continue
        opened += 1
        req_id = job.url.rsplit("/", 1)[-1]
        try:
            d = http.get(detail_api, params={
                "onlyData": "true",
                "finder": f'ById;Id="{req_id}",siteNumber={site}',
            }).json()
            item = (d.get("items") or [{}])[0]
            parts = [item.get(k, "") for k in ("ExternalDescriptionStr", "ExternalQualificationsStr",
                                              "ExternalResponsibilitiesStr")]
            job.description = html_to_text(" ".join(p for p in parts if p)) or job.description
            job.closing = iso_date(item.get("ExternalPostedEndDate")) or job.closing
        except Exception:
            pass
    return jobs
