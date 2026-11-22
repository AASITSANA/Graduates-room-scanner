# The Graduates Room SA – Job Scanner

Every morning this scanner visits the careers portals of 221 South African employers, keeps only
**graduate and entry-level jobs in South Africa**, and publishes them as one file,
`data/jobs.json`, that your website reads.

It does not search the web or guess. It reads each company's own job portal, so every job it
lists is a real, live ad with its real link.

---

## How it works

1. **`companies.csv`** is the list of employers. For each one it holds the hiring platform the
   company uses (`platform`) and where its jobs live (`feed_url`).
2. **`discover.py`** fills in those two columns automatically by visiting each company's website.
3. **`run.py`** reads every company's jobs, filters them and writes:
   - `data/jobs.json` – all live graduate jobs (this is what the website shows)
   - `data/new_today.json` – jobs found for the first time today
   - `data/report.md` – which companies worked, which failed, and how many jobs each had
4. **GitHub Actions** runs it every day at 05:17 and saves the results. It's free.

### Platforms it can read
| Platform | Used by (examples) | `feed_url` looks like |
|---|---|---|
| Workday | many banks, miners, multinationals | `https://absa.wd3.myworkdayjobs.com/ABSAcareersite` |
| SAP SuccessFactors | Vodacom, SAP and others | `https://opportunities.vodafone.com/Vodacom/search/` |
| Oracle Recruiting | SARB | `https://…oraclecloud.com/hcmUI/CandidateExperience/en/sites/SARB/jobs` |
| Greenhouse | Takealot | `takealotcom` |
| Lever / Workable / SmartRecruiters | tech companies | the board name, e.g. `clickatell` |
| `html` (catch-all) | anyone else | the careers page address |
| `dpsa` | the Public Service vacancy circular | `https://www.dpsa.gov.za/newsroom/psvc/` |

### How it decides a job is for graduates
- **Kept:** titles with graduate, intern, trainee, learnership, candidate attorney, junior,
  early careers and similar wording.
- **Kept, but marked `"confidence": "check"`:** plain titles such as "Data Analyst", only when the
  ad says recent graduates are welcome or asks for at most 1 year of experience.
- **Dropped:**
  - senior, manager, lead and specialist roles
  - jobs asking for 3+ years' experience
  - bursaries and vacation work
  - matric-only learnerships
  - expired ads
  - jobs outside South Africa
- **Tagged:** job type, faculty (Commerce, Engineering, IT, Law, Science, Humanities, Health,
  Built Environment) and province.

---

## Setting it up (once, about 20 minutes)

1. **Create a free GitHub account** at github.com if you don't have one.
2. **Create a new repository.** Click **+ → New repository** and name it `graduates-room-scanner`.
   Choose **Public**: GitHub Actions is free and unlimited for public repositories, and your
   website can read the results directly.
3. **Upload the files.** On the new repository page, click **uploading an existing file** and
   drag in everything from this folder, including the `.github` folder. Then click **Commit changes**.
   > If the `.github` folder doesn't upload by dragging, create the two workflow files by hand:
   > **Add file → Create new file**, name it `.github/workflows/daily-scan.yml` and paste
   > its contents. Do the same for `find-platforms.yml`.
4. **Allow the robot to save results.** Go to **Settings → Actions → General → Workflow
   permissions**, choose **Read and write permissions**, and click **Save**.
5. **Find each company's platform.** Go to the **Actions** tab and click **Find hiring platforms → Run workflow**.
   It takes about 10–20 minutes. Afterwards, `companies.csv` is filled in and
   `data/discover_report.md` lists what it found for each company.
6. **Run the first scan.** In the Actions tab, click **Daily graduate job scan → Run workflow**.
   When it's done, open `data/report.md` and `data/jobs.json`.
7. From now on it **runs by itself every morning**.

### Optional: AI second opinion
Jobs marked `check` can be reviewed by Claude before they're published.
1. Get an API key at console.anthropic.com.
2. In your repository, go to **Settings → Secrets and variables → Actions → New repository secret**.
   Name it `ANTHROPIC_API_KEY` and paste the key.

It checks at most 60 jobs a run. The AI only reads ads the scanner already found, so it never
searches the web or invents jobs.

---

## Showing the jobs on your website

Your site can load the list straight from GitHub. Replace `YOUR-GITHUB-NAME`:

```html
<div id="jobs"></div>
<script>
fetch("https://raw.githubusercontent.com/YOUR-GITHUB-NAME/graduates-room-scanner/main/data/jobs.json")
  .then(r => r.json())
  .then(data => {
    document.getElementById("jobs").innerHTML = data.jobs.map(j => `
      <article class="job">
        <h3>${j.title}</h3>
        <p>${j.company} · ${j.location || "South Africa"} · ${j.job_type}</p>
        <p>Faculty: ${j.faculties.join(", ")} · Closes: ${j.closing_date || "Not stated"}</p>
        <a href="${j.url}" target="_blank" rel="noopener">Apply on ${j.company}'s site</a>
      </article>`).join("");
  });
</script>
```
To browse by faculty, filter the list: `data.jobs.filter(j => j.faculties.includes("Law"))`.

Each job in `jobs.json` looks like this:
```json
{
  "id": "8bde05d2a4dc2726", "title": "Graduate Developer 2027", "company": "Takealot Group",
  "sector": "Technology", "location": "Cape Town, South Africa", "province": "Western Cape",
  "job_type": "Graduate programme", "faculties": ["IT"], "closing_date": "2027-01-15",
  "posted_date": null, "url": "https://…", "first_seen": "2026-11-22", "last_seen": "2026-11-22",
  "confidence": "high"
}
```

---

## Looking after it (10 minutes a week)

- **Open `data/report.md`.** Companies marked `ERROR` or `skipped` need attention.
- **To fix a company:**
  1. Open its careers page in your browser and click through to the job list.
  2. Copy that address into the company's `feed_url` in `companies.csv`.
  3. Set `platform` using the table above. If no platform matches, use `html`.
- **To test one company:** go to **Actions → Daily graduate job scan → Run workflow** and type the
  company name in the box.
- **To pause a company:** set `active` to `no`.
- **To add a company:** add a row with `platform` left empty, then run **Find hiring platforms** again.
- **`global` column:** `yes` means the portal lists jobs worldwide, so the scanner only keeps jobs
  that name a South African place.

## Running it on your own computer (optional)
```
pip install -r requirements.txt
python -m pytest -q tests          # self-test, no internet needed
python discover.py --only Absa     # find one company's platform
python run.py --only Takealot --show-raw
```

## Rules it follows
- It waits at least 1 second between requests to the same website, and identifies itself in
  every request.
- It only reads public careers pages, once a day.
- It never touches LinkedIn, Indeed or other job boards, whose terms forbid scraping.
