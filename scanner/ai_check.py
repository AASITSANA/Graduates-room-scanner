"""Optional second opinion from Claude on jobs the rules marked 'check'.

Only runs when the ANTHROPIC_API_KEY secret is set. The AI never searches the web: it only
reads an ad the scanner already found, so it cannot invent jobs. If anything fails, the job
keeps its rule-based result.
"""
import json
import os
import re

import requests

MODEL = os.environ.get("AI_MODEL", "claude-haiku-5-5")
MAX_CHECKS = int(os.environ.get("AI_MAX_CHECKS", "60"))  # per run, to cap cost

PROMPT = """You screen job ads for a South African website that only lists jobs for recent graduates.
Read the ad and answer with JSON only:
{"graduate_level": true/false, "reason": "<10 words", "closing_date": "YYYY-MM-DD" or null,
 "faculties": [up to 3 of "Commerce","Engineering","IT","Law","Science","Humanities","Health",
 "Built Environment","All faculties"]}
graduate_level is true only if a recent graduate (0-2 years' experience) could realistically apply.

Title: {title}
Company: {company}
Location: {location}
Ad text:
{text}"""


def enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def review(job, description: str) -> dict | None:
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 200,
                "messages": [{"role": "user", "content": PROMPT
                              .replace("{title}", job.title)
                              .replace("{company}", job.company)
                              .replace("{location}", job.location or "not stated")
                              .replace("{text}", description[:6000])}],
            },
            timeout=60,
        )
        r.raise_for_status()
        text = r.json()["content"][0]["text"]
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None
