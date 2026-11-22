"""Daily scan: read every company's job portal, keep graduate jobs, publish data/jobs.json.

Usage:
  python run.py                      # scan every active company
  python run.py --only "Takealot"    # test one company (name contains this text)
  python run.py --show-raw           # also print every job found before filtering
"""
import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

from scanner.readers import run_reader, SUPPORTED
from scanner.filter import classify
from scanner import ai_check

ROOT = Path(__file__).parent
COMPANIES = ROOT / "companies.csv"
DATA = ROOT / "data"
JOBS_FILE = DATA / "jobs.json"
NEW_FILE = DATA / "new_today.json"
REPORT = DATA / "report.md"
WORKERS = 8


def load_companies(only: str | None):
    rows = []
    with COMPANIES.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("active") or "yes").strip().lower() in ("no", "n", "0", "false"):
                continue
            if only and only.lower() not in r["company"].lower():
                continue
            rows.append(r)
    return rows


def scan_company(row):
    platform = (row.get("platform") or "").strip().lower()
    feed = (row.get("feed_url") or "").strip()
    if platform not in SUPPORTED or (not feed and platform != "dpsa"):
        return row, None, "skipped: no platform/feed yet"
    is_global = (row.get("global") or "").strip().lower() in ("yes", "y", "true", "1")
    started = time.time()
    try:
        raw = run_reader(platform, row["company"], feed, is_global)
        return row, raw, f"ok in {time.time() - started:.0f}s"
    except Exception as e:  # one broken portal must not stop the scan
        return row, None, f"ERROR {type(e).__name__}: {str(e)[:160]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--show-raw", action="store_true")
    args = ap.parse_args()

    today = date.today()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    DATA.mkdir(exist_ok=True)
    companies = load_companies(args.only)
    if not companies:
        sys.exit("No matching companies in companies.csv")

    results, report_rows, failed_companies, kept = [], [], set(), []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(scan_company, r) for r in companies]
        for fut in as_completed(futures):
            row, raw, status = fut.result()
            results.append((row, raw, status))

    for row, raw, status in sorted(results, key=lambda x: x[0]["company"]):
        is_global = (row.get("global") or "").strip().lower() in ("yes", "y", "true", "1")
        if raw is None:
            if status.startswith("ERROR"):
                failed_companies.add(row["company"])
            report_rows.append((row["company"], row.get("platform", ""), "-", "-", status))
            continue
        n_kept = 0
        for rj in raw:
            if args.show_raw:
                print(f"  [{rj.source}] {rj.company} | {rj.title} | {rj.location}")
            job = classify(rj, row.get("sector", ""), is_global, today)
            if job:
                job._description = rj.description  # used by the optional AI check only
                kept.append(job)
                n_kept += 1
        report_rows.append((row["company"], row.get("platform", ""), len(raw), n_kept, status))

    # Optional AI second opinion on borderline jobs
    if ai_check.enabled():
        checked = 0
        for job in list(kept):
            if job.confidence != "check" or checked >= ai_check.MAX_CHECKS:
                continue
            checked += 1
            verdict = ai_check.review(job, getattr(job, "_description", ""))
            if not verdict:
                continue
            if verdict.get("graduate_level") is False:
                kept.remove(job)
                continue
            job.confidence = "high"
            job.closing_date = job.closing_date or verdict.get("closing_date")
            if verdict.get("faculties"):
                job.faculties = verdict["faculties"][:3]

    # Merge with yesterday's list
    old = {}
    if JOBS_FILE.exists():
        old = {j["id"]: j for j in json.loads(JOBS_FILE.read_text(encoding="utf-8")).get("jobs", [])}
    scanned_ok = {r[0] for r in report_rows if str(r[4]).startswith("ok")}

    merged, new_jobs = {}, []
    for job in kept:
        d = job.to_dict()
        prev = old.get(job.id)
        d["first_seen"] = prev["first_seen"] if prev else today.isoformat()
        d["last_seen"] = today.isoformat()
        if not prev:
            new_jobs.append(d)
        merged[job.id] = d
    for jid, d in old.items():
        if jid in merged:
            continue
        # keep a job whose company could not be scanned today, unless it has closed
        if d["company"] in scanned_ok:
            continue  # the company was scanned and the job is gone: it was taken down
        if d.get("closing_date") and d["closing_date"] < today.isoformat():
            continue
        merged[jid] = d

    jobs = sorted(merged.values(), key=lambda j: (j.get("closing_date") or "9999", j["company"]))
    JOBS_FILE.write_text(json.dumps({"updated_at": now, "count": len(jobs), "jobs": jobs},
                                    indent=1, ensure_ascii=False), encoding="utf-8")
    NEW_FILE.write_text(json.dumps({"date": today.isoformat(), "count": len(new_jobs),
                                    "jobs": new_jobs}, indent=1, ensure_ascii=False), encoding="utf-8")

    lines = [f"# Scan report – {now}", "",
             f"- Companies in this run: {len(companies)}",
             f"- Scanned OK: {len(scanned_ok)} | Errors: {len(failed_companies)} | "
             f"Skipped (no platform yet): {sum(1 for r in report_rows if str(r[4]).startswith('skipped'))}",
             f"- Graduate jobs live: {len(jobs)} | New today: {len(new_jobs)}",
             f"- AI check: {'on' if ai_check.enabled() else 'off'}", "",
             "| Company | Platform | Jobs found | Graduate jobs kept | Status |",
             "|---|---|---|---|---|"]
    lines += [f"| {c} | {p} | {a} | {k} | {s} |" for c, p, a, k, s in report_rows]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines[:7]))
    for d in new_jobs[:40]:
        print(f"NEW  {d['company']}: {d['title']} ({d['location'] or 'SA'}) closes {d['closing_date']}")


if __name__ == "__main__":
    main()
