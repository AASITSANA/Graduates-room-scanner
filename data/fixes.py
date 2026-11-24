"""Hand-checked corrections, applied every time discover.py runs.

Use this for companies whose website blocks robots or hides its job portal: find the portal
yourself (or ask Claude), then add a line here. discover.py copies these values into
companies.csv. Set "keep": True on a row in companies.csv by writing 'manual' at the start of its
notes if you edit it by hand and don't want discover.py to touch it.

Keys are company names exactly as they appear in companies.csv.
"""

FIXES = {
    # Standard Bank Group posts all its jobs (including Liberty's) on one SmartRecruiters board
    "Standard Bank": {"platform": "smartrecruiters", "feed_url": "StandardBankGroup",
                      "notes": "fix: Standard Bank Group SmartRecruiters board (includes Liberty)"},
    "Liberty": {"active": "no", "notes": "fix: covered by the Standard Bank Group board"},

    # FirstRand (FNB, RMB, WesBank) shares one Workday portal
    "FNB (FirstRand)": {"platform": "workday", "feed_url": "https://firstrand.wd3.myworkdayjobs.com/FRB",
                        "notes": "fix: FirstRand Workday portal (FNB, RMB, WesBank)"},
    "RMB (FirstRand)": {"active": "no", "notes": "fix: covered by the FNB (FirstRand) row"},

    "Old Mutual": {"platform": "workday",
                   "feed_url": "https://oldmutual.wd3.myworkdayjobs.com/Old_Mutual_Careers",
                   "notes": "fix: Old Mutual Workday portal"},
    "Capitec Bank": {"platform": "successfactors", "feed_url": "https://careers.capitecbank.co.za/search/",
                     "notes": "fix: Capitec SuccessFactors career site"},

    # eRecruit portals (a South African hiring platform)
    "Shoprite Group": {"platform": "html",
                       "feed_url": "https://shoprite.erecruit.co/candidateapp/jobs/browse/",
                       "notes": "fix: Shoprite eRecruit portal"},
    "PwC": {"platform": "html", "feed_url": "https://pwcza-graduate.erecruit.co/candidateapp/jobs/browse/",
            "notes": "fix: PwC South Africa graduate eRecruit portal"},

    # SAP's career site refuses automated visitors (403), so leave it out rather than push past it
    "SAP Africa": {"active": "no", "notes": "fix: career site blocks automated visitors"},

    "Unilever South Africa": {"platform": "html",
                              "feed_url": "https://careers.unilever.com/location/south-africa-jobs/34155/953987/2",
                              "notes": "fix: Unilever careers – South Africa jobs list"},
}
