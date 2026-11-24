"""Maps the 'platform' column in companies.csv to the reader that handles it."""
from . import ats_simple, workday, successfactors, oracle, html_page, dpsa


def run_reader(platform: str, company: str, feed: str, is_global: bool):
    platform = (platform or "").strip().lower()
    if platform == "greenhouse":
        return ats_simple.greenhouse(company, feed)
    if platform == "lever":
        return ats_simple.lever(company, feed)
    if platform == "workable":
        return ats_simple.workable(company, feed)
    if platform == "smartrecruiters":
        return ats_simple.smartrecruiters(company, feed)
    if platform == "workday":
        return workday.read(company, feed)
    if platform == "successfactors":
        return successfactors.read(company, feed, south_africa_only=is_global)
    if platform == "oracle":
        return oracle.read(company, feed)
    if platform == "html":
        return html_page.read(company, feed)
    if platform == "dpsa":
        return dpsa.read(company, feed)
    raise ValueError(f"unknown platform '{platform}' – run discover.py or fill it in by hand")


SUPPORTED = ["workday", "successfactors", "greenhouse", "lever", "workable",
             "smartrecruiters", "oracle", "html", "dpsa"]
