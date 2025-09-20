### Caching

Two cache layers accelerate scoring:

1. Resume profile cache (`resume_profile_cache.json`): stores parsed resume sections & aggregated skills. Rebuild bypass with env `SCRAPER_REBUILD_RESUME_PROFILE=1`.
2. Skill extraction cache (`skills_cache.jsonl`): per-description merged skill lists + metadata. Clear via env `SCRAPER_CLEAR_SKILL_CACHE=1` or script below.

To clear caches manually:


## Architecture Overview
See `docs/architecture.md` for the Mermaid diagram and module responsibilities (resume parsing → skill extraction → scoring → dedupe → anomaly detection → export with normalization, redaction, compliance gating).

### Schema Changes
For safe database evolution steps (adding/removing columns, bumping schema version) see `docs/migration_playbook.md`.

### Release Process
Manual tagging & publishing steps documented in `docs/release_process.md`.

#### Automated GitHub Release
Pushing an annotated tag `vX.Y.Z` triggers a GitHub Action (`.github/workflows/release.yml`) that:
1. Builds wheel + sdist
2. Extracts the corresponding CHANGELOG section
3. Creates a GitHub Release with notes
4. Uploads build artifacts

View workflow runs under the Actions tab after pushing a tag.

## Multi-Source Ingestion (Experimental)
Configure multiple job sources via `scraper/config/sources.yml`:

```yaml
sources:
    - name: mock
        enabled: true
        module: scraper.jobminer.sources.mock_source
        class: MockJobSource
        options:
            count: 5
            title: Sample Role
```

Run ingestion:
```powershell
python scraper/scripts/run_ingest.py --config scraper/config/sources.yml
```

Sources implement a simple interface (`fetch() -> List[JobPosting]`). Internal IDs are automatically namespaced (`source_name:raw_id`) to avoid collisions and enable cross-source dedupe.

### Greenhouse Adapter (Public Board API)
Fetches jobs from a company's public Greenhouse board JSON (`/embed/jobs/json`). Requires only the company slug (appears in the board URL `https://boards.greenhouse.io/<slug>`). Low-rate, read-only usage of this public endpoint; avoid rapid polling.

Config example:
```yaml
sources:
    - name: gh_example
        enabled: true
        module: scraper.jobminer.sources.greenhouse_source
        class: GreenhouseSource
        options:
            company_slug: examplecompany   # from URL
            limit: 150                     # optional cap (default 200)
            company_name: Example Company  # optional override display name
```

### Lever Adapter (Public Postings Endpoint)
Uses Lever's published JSON postings endpoint: `https://api.lever.co/v0/postings/<company_slug>?mode=json`. Also unauthenticated. We merge `descriptionHtml` + list section content for richer skill extraction.

Config example:
```yaml
sources:
    - name: lever_example
        enabled: true
        module: scraper.jobminer.sources.lever_source
        class: LeverSource
        options:
            company_slug: exampleco       # from hosted URL
            limit: 120                    # optional cap
            company_name: ExampleCo       # optional friendly name
```

### Combined Example (Multiple Sources)
```yaml
sources:
    - name: gh_example
        enabled: true
        module: scraper.jobminer.sources.greenhouse_source
        class: GreenhouseSource
        options:
            company_slug: examplecompany
            limit: 120
    - name: lever_example
        enabled: true
        module: scraper.jobminer.sources.lever_source
        class: LeverSource
        options:
            company_slug: exampleco
    - name: adzuna
        enabled: true
        module: scraper.jobminer.sources.adzuna_source
        class: AdzunaSource
        options:
            what: data engineer
            country: us
            max_pages: 2
    - name: remotive
        enabled: true
        module: scraper.jobminer.sources.remotive_source
        class: RemotiveSource
        options:
            what: python data
```

Run ingestion (same command):
```powershell
python scraper/scripts/run_ingest.py --config scraper/config/sources.yml
```

### Compliance & Safety Notes (Collection Layer)
- Only use public, unauthenticated endpoints (Adzuna requires official API keys; Greenhouse/Lever public boards are fine).
- Do not brute force company slugs; add only organizations you are genuinely tracking.
- Keep request rates modest (e.g., manual or a low-frequency scheduled run >30m apart).
- No credential capture or storage is performed by these adapters.
- For any site with explicit anti-bot clauses or needing login, prefer manual export → local JSON adapter pattern (like the Indeed loader) rather than automated scraping.
- Provide an opt-out mechanism internally (remove an entry from `sources.yml` → immediately halts collection).

Future enhancement: provenance merging to consolidate the same job across multiple sources (use canonical apply URL & fuzzy title/company matching) is planned; current behavior is simple union with ID namespacing.

### Provenance & Cross-Source De-duplication
When multiple adapters surface the same underlying job the ingestion layer merges them into a single `JobPosting` while tracking a `provenance` list (source names contributing data).

Duplicate signature logic (hierarchical):
1. Non-ATS URL host + path + simplified title (strong uniqueness). If the apply URL host is not a known ATS provider it’s assumed to be a canonical corporate application page and kept distinct.
2. For known ATS hosts (e.g. Greenhouse, Lever, Workable, SmartRecruiters) or missing URL → fallback to company + simplified title + location fragment. This enables merging the same role that appears on multiple ATS platforms for the same company (e.g., migration period) or across mirrored postings.

Merge rules:
- First encountered job becomes canonical.
- Additional duplicates append their source name to `provenance`.
- Longer description replaces a shorter one (preserves richest text for skill extraction).
- Missing salary fields are filled if a later source provides them.
- `posted_at` is retained if already set; otherwise earliest available date fills.

Known ATS host list (heuristic, extend as needed): `boards.greenhouse.io`, `jobs.lever.co`, `workable.com`, `smartrecruiters.com`.

The `job_id` remains that of the first source (already namespaced). This keeps downstream references stable while aggregating data quality. Later improvements considered (not yet implemented): fuzzy company normalization before signature, Jaro-Winkler similarity for title drift, and time-based decay to re-merge after major description edits.

CLI visibility (planned flag `--show-provenance`) will enumerate provenance sources during listing. Until then, inspect via direct DB query or full export scripts.

### Polite Rate Limiting Helper
Module: `jobminer.util.rate_limit` provides `polite_get()` which enforces a minimal interval per host (default 0.75s) plus jitter and light exponential backoff on 429 / transient 5xx. Adapters can opt-in by swapping `client.get(url)` with `polite_get(url)` to further reduce burstiness. Not enabled globally to avoid altering existing timing expectations silently.

Environment suggestion for higher courtesy on shared networks: increase interval via wrapper or local patch (e.g. `min_interval=1.2`).

### Indeed Adapter (Local JSON Loader)
To respect Terms of Service, the Indeed adapter does not perform automated scraping. Instead it loads a local JSON export you captured manually (browser save, copy/paste, or API export where permitted).

Example config entry:
```yaml
sources:
    - name: indeed
        enabled: true
        module: scraper.jobminer.sources.indeed_source
        class: IndeedJobSource
        options:
            path: data/sample/indeed_jobs.json
            limit: 25              # optional cap
            default_location: Remote
The static dashboard now includes:
- Legends for each chart series
- Hover tooltips over data points
- A "Latest Highlights" card summarizing the most recent snapshot (with deltas from the previous day when available)
- A link to the latest weekly summary when `scraper/data/daily_snapshots/weekly_summary.md` exists
    - name: mock
        enabled: true
        module: scraper.jobminer.sources.mock_source
        class: MockJobSource
        options:
            count: 3
```

Run ingestion:
```powershell
python scraper/scripts/run_ingest.py --config scraper/config/sources.yml
```

Sample file provided at `data/sample/indeed_jobs.json` to validate pipeline behavior. The adapter performs light normalization:
- Accepts varied key names for id (id | job_id | jk), title (title | job_title), company (company | company_name) and description (description | snippet | desc)
- Tries multiple date formats or epoch timestamps
- Normalizes company names by removing trailing "Inc." (case-insensitive)

Resulting jobs are namespaced as `indeed:<raw_id>` during normalization (handled by framework). This enables safe coexistence with other sources before dedupe.


## Semantic Enrichment Refinement
When the semantic toggle is enabled, a lightweight TF-IDF based `SemanticEnricher` supplements heuristic skill matches. It:
1. Tokenizes job description + seed skills (with optional bigrams)
2. Builds mini TF-IDF corpus (description + each skill phrase)
3. Computes cosine similarity of each seed phrase vector to the job description vector
4. Appends any additional seed skills above threshold not already matched, preserving the original heuristic ordering as a prefix.

Deterministic: no randomness, order = (heuristic skills) + (new semantic additions sorted by similarity then seed order). Fallback is safe—if enrichment errors, heuristic set is returned unchanged.

### Configuring Semantic Enrichment
Configuration file: `scraper/config/semantic.yml`

Keys:
- similarity_threshold (float, default 0.32): minimum cosine similarity to add a new skill
- max_new (int, default 15): cap on number of semantic-added skills
- enable_bigrams (bool, default true): include bigram tokens (e.g., "machine_learning")

Environment overrides (take precedence over file):
- SCRAPER_SEMANTIC_THRESHOLD
- SCRAPER_SEMANTIC_MAX_NEW
- SCRAPER_SEMANTIC_ENABLE_BIGRAMS (1/0, true/false)

These options are loaded lazily inside the enricher; direct constructor args also override config/env in programmatic use.

### Benchmarking Semantic Overhead
Run the benchmark script to compare heuristic-only vs semantic-enabled extraction timing and enrichment effect:
```powershell
python scraper/scripts/benchmark_semantic.py --limit 200
```
Outputs `scraper/data/benchmarks/semantic_benchmark.json` with metrics:
- heuristic_time_s / semantic_time_s
- avg_skills_heuristic / avg_skills_semantic / avg_added_semantic
- speed_ratio (semantic_time / heuristic_time)
- active config parameters (threshold, bigrams, max_new)

Use env vars (`SCRAPER_SEMANTIC_THRESHOLD`, etc.) before running to profile different settings.


## Quickstart (5 Minutes)
Follow these steps on Windows PowerShell after cloning.

### 1. Create & Activate Virtualenv
```powershell
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r scraper/requirements.txt
```

### Install as Editable Package (Optional)
You can install the project in editable mode to expose console scripts:
```powershell
pip install -e .[dev]
jobminer-export --help
```
Version is defined in `pyproject.toml` and exposed as `jobminer.__version__`.

### 2. (Optional) Install Browsers for Collector
```powershell
python -m playwright install
```

### 3. Load Sample / Mock Jobs
If you have a JSON of jobs, import with the pipeline scripts (or insert manually). For a single quick mock:
```powershell
python - <<'PY'
from scraper.jobminer.db import JobDB
from scraper.jobminer.models import JobPosting
db = JobDB()
db.upsert_jobs([JobPosting(job_id='demo1', title='Data Engineer', company_name='DemoCo', description_raw='Python SQL role', description_clean='Python SQL role')])
print('Inserted demo job')
PY
```

### 4. Score Jobs
Provide a resume PDF (place `Resume - Paris_Apostolopoulos.pdf` or your own in repo root) and a seed skills file:
```powershell
echo Python> skills.txt; echo SQL>> skills.txt; echo ETL>> skills.txt
python scraper/scripts/run_score.py --resume "Resume - Paris_Apostolopoulos.pdf" --seed skills.txt
```

### 5. Export Ranked Outputs
```powershell
python scraper/scripts/run_export.py
```
Exports appear in `scraper/data/exports/` (Excel, shortlist CSV, explanations CSV, rationale workbook).

### 6. Update Status & View Funnel
```powershell
python scraper/scripts/job_cli.py list
python scraper/scripts/job_cli.py status demo1 reviewed
python scraper/scripts/job_cli.py stats
python scraper/scripts/job_cli.py history demo1
```

### 7. View Run Summary & History
Latest run summary: `type scraper/data/run_summary.json`
Historical JSONL (appended each scoring run): `scraper/data/exports/run_history.jsonl`

### 8. Detect Anomalies
If a significant drop ( >35% vs baseline ) in average score or skills per job is detected, a warning line with `anomaly_detected` appears in logs.

### 9. Rebuild / Clear Caches (when resume changes or debugging)
```powershell
$env:SCRAPER_REBUILD_RESUME_PROFILE='1'
python scraper/scripts/run_score.py --resume "Resume - Paris_Apostolopoulos.pdf" --seed skills.txt
```
Clear skill extraction cache only:
```powershell
python -m scraper.scripts.clear_caches --skills
```

### 10. One-Command Pipeline (Collect → Score → Export)
```powershell
python scraper/scripts/run_pipeline.py --no-semantic --no-score   # dry pattern examples
```
Add searches in `config/searches.yml` then run without flags for full flow.

---

This project provides a scaffold to collect job postings (initially manual or mock ingestion), score them against your resume skills, and export ranked results.

> NOTE: Automated scraping of LinkedIn can violate their Terms of Service. Use manual or semi-manual collection or public/authorized APIs where possible.

## Components
- `jobminer.models` – Pydantic data models including salary + benefits.
- `jobminer.db` – SQLite storage (file located at `data/db.sqlite`).
- `jobminer.scoring` – Skill + semantic + recency scoring.
- `jobminer.exporter` – Exports full Excel and shortlist CSV.
 - `jobminer.collector` – Playwright collector (conservative, optional).
- `config/` – Search definitions, scoring weights, seed skills.
- `scripts/` – Utility entry points.
    - `run_mock_import.py` – Loads sample jobs for testing.
    - `run_score.py` – Parses resume and scores all jobs.
    - `run_export.py` – Exports Excel + CSV.
    - `job_cli.py` – Simple CLI for listing / updating job status.
    - `run_collect.py` – Collects jobs via Playwright (requires login once).

## Setup
Create a Python 3.11+ virtual environment.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r scraper/requirements.txt
Playwright browsers (first time only):

```
python -m playwright install
```
```

## Mock Usage Flow
1. Insert mock jobs (sample snippet below) using an interactive Python session.
2. Run export script.

```
python scraper/scripts/run_export.py
```

### Insert Mock Job Example
```python
from jobminer.db import JobDB
from jobminer.models import JobPosting

db = JobDB()
job = JobPosting(
    job_id="123",
    title="Data Analyst",
    company_name="Example Corp",
    location="Remote - US",
    skills_extracted=["sql","python","power bi"],
    description_raw="We need a data analyst...",
    description_clean="We need a data analyst to build dashboards...",
    seniority_level="Associate",
    offered_salary_min=80000,
    offered_salary_max=95000,
    offered_salary_currency="USD",
    benefits=["401k","health insurance"],
)

db.upsert_jobs([job])
```

## Next Steps

## Collector Usage (Optional, ToS risk)
1. Ensure dependencies installed and run `python -m playwright install` once.
2. Run `python scraper/scripts/run_collect.py` with `headless=False` (default). A browser will open. Log in to LinkedIn once; the profile is stored in `scraper/data/browser_profile`.

Safety: keep run frequency low, add delays, avoid parallelism, and respect site policies.

- Playwright, Pydantic models, and rapidfuzz are imported only when needed.

Environment flags (set before importing modules):

```
# Skip creating rotating file logs
set SCRAPER_DISABLE_FILE_LOGS=1   (Windows PowerShell: $env:SCRAPER_DISABLE_FILE_LOGS='1')
# Skip structured event JSON lines
set SCRAPER_DISABLE_EVENTS=1
```

With both flags set, `import scraper.jobminer.collector` typically completes in ~0.2s on a warm disk.

### Parallel Skill Extraction
Set worker threads for skill extraction & semantic enrichment:

CLI: `--max-workers 4`

Env: `SCRAPER_MAX_WORKERS=4`

Defaults to 1 (serial). Safe because database writes occur serially and shared caches are lock-protected. Measure speedup; beyond ~4 workers may yield diminishing returns.

An automated test (`test_import_performance.py`) asserts import stays below a ceiling (<0.35s) for CI variability.

### Streaming Export Mode
For large job sets you can reduce memory by enabling streaming export. Instead of building full in-memory DataFrames and Excel workbooks, rows are written incrementally.

Enable (precedence: explicit parameter in code > env var):

PowerShell example:
```
$env:SCRAPER_STREAM_EXPORT='1'
python scraper/scripts/run_export.py
```

Artifacts in streaming mode:

Excel files (`jobs_full.xlsx`, `jobs_rationale.xlsx`) are skipped to avoid memory overhead. Remove the env var to restore original Excel outputs.

Automated test `test_streaming_export.py` verifies streaming and non-streaming CSV parity.

### CSV Column Reference
The current web download ("slim" CSV produced by `/api/jobs/{id}/download`) intentionally exports a reduced column set focused on ranking & actionability. Some normalization/debug fields documented earlier (e.g. `company_name_normalized`, `location_normalized`, `offered_salary_min_usd`, `offered_salary_max_usd`, `geocode_lat`, `geocode_lon`) are not present in the slim file and are therefore removed from this reference to avoid confusion.

Slim CSV columns (in order):
`title, company_name, location, work_mode, employment_type, posted_at, offered_salary_min, offered_salary_max, offered_salary_currency, salary_period, salary_is_predicted, skill_score, skill_precision, skill_recall, skill_overlap_count, skill_core_size, semantic_score, score_total, matched_skills, apply_url, top_skills`

Future enhancement: a "full" export (already supported by the backend exporter for offline runs) includes additional normalization and provenance fields; when (or if) exposed via the web flow those columns will be re-documented here.

| Column | Description | Notes |
|--------|-------------|-------|
| title | Job title | Raw source text (may undergo redaction if enabled). |
| company_name | Company name | Raw source; may be redacted. |
| location | Location string | Unnormalized display value. |
| work_mode | remote / hybrid / onsite | Derived or source-provided. |
| employment_type | full_time / part_time / contract etc. | Blank if unavailable. |
| posted_at | ISO date published | Date only (UTC). |
| offered_salary_min / offered_salary_max | Salary range bounds | Authoritative API values preferred; may be filled by heuristic extraction. |
| offered_salary_currency | Currency code | From source or inferred from symbol. |
| salary_period | Salary period | Often 'yearly'; retained from source when available. |
| salary_is_predicted | Source prediction flag | Direct passthrough if present. |
| salary_heuristic_extracted | Flag when range inferred from description | Indicates provenance when authoritative salary absent. |
| skill_score | Weighted overlap score (IDF-like) | See Skill Metrics section below. |
| skill_precision | Weighted overlap / weighted job skill mass | Diagnostic (0–1). |
| skill_recall | Weighted overlap / weighted core resume mass | Diagnostic (0–1). |
| skill_overlap_count | Distinct overlapping skills | Case-insensitive count. |
| skill_core_size | Size of adaptive core subset | Half of resume skills clamped [8,24]. |
| semantic_score | Embedding/fuzzy similarity | 0 if semantic disabled/unavailable. |
| score_total | Final composite score | Weighted sum (see weights config). |
| matched_skills | Ordered merged skill list | Overlap → extracted → responsibility/semantic additions. |
| apply_url | Application or fallback URL | Fallback constructed when absent. |
| top_skills | First 5 matched skills | Convenience subset for quick scan. |

Rationale / explanation CSV (`jobs_explanations.csv`) adds: `recency_score`, `seniority_component`, `base_extracted`, `resume_overlap`, `overlap_added`, `semantic_added`, `rationale_text`, and snapshot JSON blobs for `weights`, `thresholds`, and `matching` configuration.

### Skill Metrics (Detailed)
These diagnostic fields help explain why two jobs with similar raw overlap counts can end up with different `skill_score` values.

Terminology:
- R = Ordered resume skill list (after parsing). An adaptive core subset C is taken from the first portion of R.
- C = Core resume skill subset (size = min(24, max(8, floor(0.5 * |R|)))). Only C is used for recall denominator.
- J = Set of unique job skills extracted (`matched_skills`).
- O = C ∩ J (overlapping core skills, case-insensitive).
- w(s) = Weight for skill s. If global frequency map available: w(s) = 1 + log(1 + (N / (1 + f_s))) where N = number of jobs processed, f_s = number of jobs containing s (IDF-like). If no freq map, a lightweight fallback weight (1 + len(s)/40) is used.

Computed values:
1. Weighted overlap: W_O = Σ_{s∈O} w(s)
2. Job mass: W_J = Σ_{s∈J} w(s)
3. Core mass: W_C = Σ_{s∈C} w(s)
4. Precision = W_O / W_J (how concentrated the job's skills are on your core)
5. Recall = W_O / W_C (how much of your core the job covers)
6. Harmonic mean (F1) = 2 * Precision * Recall / (Precision + Recall)
7. Breadth bonus = min(0.08, 0.08 * (W_O / (0.35 * W_C)))   d for covering a healthy fraction of the weighted core.
8. skill_score = min(1.0, F1 + breadth bonus)

Additional counters:
- `skill_overlap_count` = |O| (unweighted count)
- `skill_core_size` = |C|

Example A (Focused Match):
- Core C size = 12; overlapping O size = 6; those 6 are relatively uncommon (higher weights) giving W_O = 7.5
- W_J = 9.0 (job lists 10 skills, 6 overlap)
- W_C = 13.0
- Precision = 7.5 / 9.0 = 0.833
- Recall = 7.5 / 13.0 ≈ 0.577
- F1 ≈ 0.684
- Breadth ratio = 7.5 / (0.35 * 13.0) ≈ 1.65 → bonus capped at 0.08
- skill_score ≈ 0.764

Example B (Broad but Shallow):
- Same core size (12). Overlap count still 6, but overlapping skills are very common → W_O = 4.2
- W_J = 15.0 (job lists many additional generic skills)
- W_C = 13.0
- Precision = 4.2 / 15.0 = 0.28
- Recall = 4.2 / 13.0 ≈ 0.323
- F1 ≈ 0.300
- Breadth ratio = 4.2 / (0.35 * 13.0) ≈ 0.924 → bonus = 0.08 * 0.924 ≈ 0.074
- skill_score ≈ 0.374

Interpretation: Both jobs overlapped on 6 core skills, but pervasive (high-frequency) skills contribute less weight, lowering both precision and recall in Example B; the breadth bonus partially offsets recall limitations but cannot close the gap fully.

Quick Heuristics When Reading Rows:
- High precision & lower recall → Niche job strongly aligned to a subset of your core; consider if missing core skills are acceptable.
- High recall & lower precision → Broad coverage but job lists many extra generic or irrelevant skills.
- Overlap count near core size with balanced precision/recall → Strong overall fit (expect higher composite score given weights).
- Very low precision (<0.2) even if overlap count moderate → Signal dilution; review unmatched core skills.

#### Salary Provenance Logic
If authoritative salary fields are absent the exporter scans the description (first ~8000 chars) for bounded ranges with a currency symbol (unless `JOBMINER_SALARY_REQUIRE_SYMBOL=0`) and filters out suspiciously tiny values (`JOBMINER_SALARY_MIN_YEARLY`, default 70000). Successful extraction sets `salary_heuristic_extracted=true` and populates missing min/max (and currency if derivable from symbol).

### Key Environment Variables (New / Updated)
| Variable | Purpose | Default | Notes / Precedence |
|----------|---------|---------|--------------------|
| JOBMINER_TOKEN_TTL_MINUTES | Lifetime of download/job tokens | 60 | Upper bound 1440 (24h). |
| JOBMINER_MAX_PAGES | Force max pages for Adzuna fetch | dynamic | Overrides adaptive paging when set (1–10). |
| JOBMINER_RESULTS_PER_PAGE | Force results per page for Adzuna fetch | dynamic | Overrides adaptive per-page size (1–50). |
| JOBMINER_SALARY_MIN_YEARLY | Minimum accepted inferred yearly salary (heuristic) | 70000 | Applied only to heuristic extraction. |
| JOBMINER_SALARY_REQUIRE_SYMBOL | Require currency symbol in heuristic range | 1 (true) | Set 0/false to allow symbol-less numeric ranges. |
| SCRAPER_STREAM_EXPORT | Enable streaming export mode | off | Reduces memory; disables Excel outputs. |
| SCRAPER_REDACT_EXPORT | Force redaction on/off | config default | CLI flag or env overrides config. |
| SCRAPER_MAX_WORKERS | Threads for extraction phase | 1 | >1 enables parallel extraction (skill phase). |
| SCRAPER_SEMANTIC_BENCH / SCRAPER_SEMANTIC_BENCH_LIMIT | Embed semantic benchmark metrics / sample size | off / 10 | Observability only. |
| SCRAPER_NO_SEMANTIC | Force disable semantic similarity layer | off | Highest semantic precedence (overrides enable). |
| SCRAPER_SEMANTIC_ENABLE | Explicitly enable/disable semantic (0/1) | unset | Precedence: NO_SEMANTIC > SEMANTIC_ENABLE > matching.yml. |
| SCRAPER_SEMANTIC_THRESHOLD / SCRAPER_SEMANTIC_MAX_NEW / SCRAPER_SEMANTIC_ENABLE_BIGRAMS | Tune semantic enricher | see config | Applied when semantic enabled. |
| SCRAPER_REBUILD_RESUME_PROFILE | Rebuild cached resume profile | off | Useful after resume edits. |
| SCRAPER_CLEAR_SKILL_CACHE | Clear JSONL skill cache pre-run | off | Forces fresh extraction for all jobs. |
| SCRAPER_DISABLE_FILE_LOGS / SCRAPER_DISABLE_EVENTS | Skip file logs / structured events | off | Speeds iteration; reduces disk IO. |

Semantic toggle resolution order (highest → lowest): explicit function call override (internal), `SCRAPER_NO_SEMANTIC=1`, `SCRAPER_SEMANTIC_ENABLE=0/1`, config file `matching.yml` (`semantic.enable`), fallback default = enabled.

### Debugging Skill Scores
Use the precision/recall/overlap/core size fields to reason about why two jobs with similar raw overlap counts might diverge in `skill_score` (frequent skills get down‑weighted via IDF-like weighting). A broad but shallow overlap can have lower recall; a concentrated overlap on core resume skills boosts recall and thus F1.


### Compensation & Benefit Normalization
Exports now include additional columns for salary conversion and normalized benefits:

Added columns:
- offered_salary_currency (original currency code if available)
- offered_salary_min_usd / offered_salary_max_usd (converted & annualized to base currency, default USD)
- benefits_normalized (canonical benefit keywords)

Configuration (edit YAML under `config/`):
- `compensation.yml` controls `base_currency`, `currency_rates`, and `unit_multipliers` (e.g., hourly → 2080).
- `benefits.yml` maps variant phrases to canonical benefit labels.

If a currency is missing from `currency_rates`, the USD normalized fields are left blank for that job.
Benefit mapping uses case-insensitive exact or contained phrase matches (ignoring very short tokens) to reduce noise.
Test coverage: `test_comp_norm.py` exercises conversion, unknown currency fallback, and benefit mapping.

### Export Redaction (PII/Sensitive Data)
To mask potential PII in exports (emails, phone numbers, URLs) enable redaction:

PowerShell examples:
```
# Via CLI flag
python scraper/scripts/run_export.py --redact

# Or for full pipeline
python scraper/scripts/run_pipeline.py --redact --stream-export

# Or environment override
$env:SCRAPER_REDACT_EXPORT='1'
python scraper/scripts/run_export.py
```

Configuration: `config/redaction.yml`
- enabled: true|false
- rules: regex patterns (merged with defaults) keyed by label
- replacement: string to substitute (default `[REDACTED]`)

Default rules cover basic email, loose phone, and URL patterns. Patterns are applied case-insensitively to selected text fields (title, company_name, location, matched_skills, apply_url). Adjust the regex cautiously—overly broad patterns could remove useful content.

Tests: `test_redaction.py` validates email and URL redaction.

### Automated Collection Compliance Gate
Automated collection is blocked unless explicitly allowed. This encourages mindful, low-volume use and alignment with site Terms of Service.

Enable automation using one of:
1. CLI flag: `--allow-automation` (pipeline script)
2. Env var: `$env:SCRAPER_ALLOW_AUTOMATION='1'`
3. Config file: `config/compliance.yml` with `allow_automation: true`

If none are present, the pipeline halts before starting collection. Scoring and export on existing data can still run (e.g., by using `--no-score --no-export` combinations or enriching only). Test: `test_compliance.py` covers flag, env, and config behaviors.

### Property-Based Testing (Hypothesis)
Property tests exercise the skill extraction heuristics across randomized synthetic descriptions to harden against regressions.

Invariants checked (`test_property_skills.py`):
- Determinism: same input → same output
- No empty skill strings
- Output subset of provided seed skills
- Resume overlap subset invariant
- Idempotence: re-running on text augmented with its own output doesn’t introduce unrelated new skills

Run a focused property suite:
```
pytest -k property_skills -q
```
Adjust max examples or deadlines in the test decorator if performance envelopes change.
## Development Quality Hooks (pre-commit)

This repo includes a `.pre-commit-config.yaml` with:

- Core hygiene hooks (trailing whitespace, large files, merge conflict markers, JSON/YAML validity)
- `ruff` (auto-fix) + `ruff-format`
- `mypy` (skips tests for speed)
- Fast pytest subset (excludes `@pytest.mark.slow`) on commit
- Full test run on push

Setup once after creating / activating your virtualenv:

```powershell
pip install -r requirements-dev.txt
pre-commit install           # enable pre-commit hooks
pre-commit install --hook-type pre-push  # enable pre-push hook
```

Run all hooks against the repo (first run may be slower):

```powershell
pre-commit run --all-files
```

Manually invoke the coverage XML hook (optional badge refresh):

```powershell
pre-commit run coverage-xml
```

Temporarily skip hooks (not recommended; use for emergency commits only):

```powershell
git commit -m "wip" --no-verify
```

If `ruff` or `mypy` fail, fix issues then re-run the failing hook or just stage changes and commit again.

### Flaky Test Reruns

For a small number of non-deterministic tests you can mark them with `@pytest.mark.flaky` and use reruns to reduce noise:

PowerShell helpers:
```powershell
# Run only flaky tests with 2 reruns (default)
scripts/test_flaky.ps1

# Increase reruns / add keyword filter
scripts/test_flaky.ps1 -Reruns 3 -Keyword cache

# One-off manual invocation
pytest -m flaky --reruns 2 --reruns-delay 1 -q
```

Keep the flaky list short; prefer fixing root causes. CI can add `--reruns` for specific jobs if needed rather than globally masking issues.

### CI Auto-Rerun Logic

The GitHub Actions workflow performs a two-phase strategy:

1. Initial run collects coverage (XML) and records failures.
2. If failures occurred, ONLY tests marked `@pytest.mark.flaky` among the failures are re-run (others fail immediately) using `--reruns N` (default N=2, configurable via `RERUN_FLAKY_COUNT`).
3. Coverage is appended (`--cov-append`) and an HTML report is generated (and badge updated) if non-flaky tests passed and flaky tests either passed on retry or were absent.
4. Non-flaky failures cause an immediate job failure (no masking). Flaky tests that still fail after N reruns also fail the job.

This reduces noise from transient issues while still surfacing persistent failures.

## End-to-End Pipeline Script
Use `scripts/run_pipeline.py` to chain collection → scoring → export in one command.

Basic examples (PowerShell):
```
python scraper/scripts/run_pipeline.py --keywords "Manager" --location "San Francisco Bay Area" --limit 40
python scraper/scripts/run_pipeline.py --headless --no-semantic
python scraper/scripts/run_pipeline.py --dry-run   # show planned searches only
python scraper/scripts/run_pipeline.py             # uses searches.yml by default
```

Key flags:
- `--keywords/--location/--geo-id`  Ad-hoc single search (bypasses searches.yml)
- `--limit`                         Override per-search limit
- `--headless`                      Headless browser collection
- `--abort-if-login`                Abort if login page detected (non-interactive)
- `--no-score` / `--no-export`      Skip downstream steps
- `--resume` / `--seed`             Override resume PDF and seed skills path
- `--no-semantic`                   Temporarily disable semantic skill mapping layer
- `--dry-run`                       Don’t launch browser; print searches and exit

Output:
- Logs (unless disabled) under `scraper/logs/`
- Exports under `scraper/data/exports/`
- Structured events appended to `collector.events.jsonl` (disable via env vars below)

Optional observability:
- Set `$env:SCRAPER_SEMANTIC_BENCH='1'` to embed a semantic enrichment benchmark snapshot into the run summary. Optionally cap sampled jobs with `$env:SCRAPER_SEMANTIC_BENCH_LIMIT` (default 10). Metrics are also written to `scraper/data/benchmarks/semantic_benchmark.json`.

Recommended before first run:
```
python -m playwright install
```

Environment optimizations (optional):
```
$env:SCRAPER_DISABLE_FILE_LOGS='1'
$env:SCRAPER_DISABLE_EVENTS='1'
$env:SCRAPER_SEMANTIC_BENCH='1'         # include semantic benchmark metrics in summary
$env:SCRAPER_SEMANTIC_BENCH_LIMIT='15'  # sample size for the benchmark (optional)
```

## Daily Snapshot 📈
Capture a small daily snapshot of key metrics for trend tracking.

Basic usage (PowerShell):
```
python scraper/scripts/daily_snapshot.py               # compute snapshot only
python scraper/scripts/daily_snapshot.py --score-first # run a quick scoring pass first
```

Outputs:
- `scraper/data/daily_snapshots/YYYY-MM-DD.json`
- `scraper/data/daily_snapshots/history.jsonl` (append-only)

Tip: Use Windows Task Scheduler to run once a day. Create a Basic Task and set the Action to start a program:
- Program/script: your Python executable
- Add arguments: `scraper/scripts/daily_snapshot.py --score-first`
- Start in: repository root directory

## Weekly Summary 🗓️
Produce a concise weekly Markdown report from snapshot history.

Usage (PowerShell):
```
python scraper/scripts/weekly_summary.py                # last 7 days
python scraper/scripts/weekly_summary.py --days 14      # last 14 days
python scraper/scripts/weekly_summary.py --json         # print JSON summary to stdout
```

Outputs:
- `scraper/data/daily_snapshots/weekly_summary.md`

You can schedule this weekly (or after the daily snapshot) using Windows Task Scheduler similarly to the daily job.

## Simple HTML Dashboard 📊
Generate a lightweight static dashboard from daily snapshots.

Usage (PowerShell):
```
python scraper/scripts/generate_dashboard.py
```

Output:
- `scraper/data/dashboard/index.html`

Open the HTML file in your browser. Consider scheduling it after the daily snapshot to keep visuals fresh.

### Semantic Enrichment Toggle
The semantic layer (sentence embeddings to infer extra skills) can be disabled three ways (precedence highest first):
1. CLI flag: `--no-semantic` (passed to pipeline scripts).
2. Env vars: `SCRAPER_NO_SEMANTIC=1` (force off) or `SCRAPER_SEMANTIC_ENABLE=0/1`.
3. Config file: `config/matching.yml` under `semantic.enable: true|false`.

If none provided, default = enabled. Disabling skips embedding model load and semantic skill inference (`skills_meta.semantic_added` stays empty).

### Duplicate & Near-Duplicate Detection
The pipeline marks duplicates in two phases:
1. Deterministic signature: `company|location|clean_title|optional_desc_prefix`. Later matches => status `duplicate`.
2. Near-duplicate (similarity) pass (enabled by default): buckets by company+location, then for each pair with fuzzy title score >= threshold (default 90) computes Jaccard similarity of description tokens. If Jaccard >= 0.82 the newer job is marked duplicate.

Tuning (in code via `detect_duplicates` params):
- `desc_prefix` (int) include leading description text in primary signature.
- `enable_similarity` toggle second pass.
- `jaccard_min` adjust sensitivity (raise to reduce false positives).
- `title_fuzzy_min` fuzzy title threshold.

Duplicates are excluded from exports and funnel metrics treat them as non-progressing.

### Windows Task Scheduler Example
1. Create a basic task → Daily.
2. Action: Start a program.
3. Program/script:
```
powershell.exe
```
4. Arguments (adjust path):
```
-NoProfile -ExecutionPolicy Bypass -Command "cd 'C:\Users\<YOU>\OneDrive\Documents\Scraper'; $env:SCRAPER_DISABLE_FILE_LOGS='1'; $env:SCRAPER_DISABLE_EVENTS='1'; .\.venv\Scripts\python scraper\scripts\run_pipeline.py --headless --no-semantic"
```
5. Start in:
```
C:\Users\<YOU>\OneDrive\Documents\Scraper
```

Add a delay or random sleep inside the command if you want to stagger collection times.


## Disclaimer
Use responsibly and respect site policies.

## Web UI (MVP) Quickstart
This repository now includes a minimal web workflow to upload a resume, search Adzuna for jobs, score them, and download a ranked CSV (≤100 rows).

### GitHub Pages Hosting Note
If you enabled GitHub Pages for this repository (e.g. https://papostolopoulos.github.io/Scraper/) the `index.html` in the repo root is a static client only. It cannot perform scoring; it sends requests to a running FastAPI backend. You must either:
1. Run `uvicorn scraper.web.server:app --port 8000` locally (default assumed base `http://127.0.0.1:8000`), or
2. Deploy the FastAPI backend elsewhere and enter that URL in the API Base override field on the page.

The page persists your chosen API base in `localStorage` under `JOBMINER_API_BASE`.

### 1. Environment Setup (PowerShell)
```powershell
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -e .
```

### 2. Configure Adzuna Credentials
Obtain an app id/key from Adzuna and set them (per session):
```powershell
$env:ADZUNA_APP_ID = "<your_app_id>"
$env:ADZUNA_APP_KEY = "<your_app_key>"
```

### 3. Run the API Server
```powershell
uvicorn scraper.web.server:app --reload --port 8000
```
Server endpoints:
- POST `/api/prepare` – accepts multipart form (resume file + fields)
- GET  `/api/download?token=...` – returns CSV for issued token
- GET  `/health` – basic status (tokens, rate usage)

### 4. Open the Form
Open `scraper/web/index.html` in your browser (double‑click works). Fill in:
- Resume file (.pdf / .doc / .docx, ≤5MB)
- Title (e.g., Data Engineer)
- Location (e.g., New York, NY)
- Distance (miles, 0–250)

Submit – a JSON response returns `{ "token": "<id>", "count": N }`.

### 5. Download Results
Use the token to fetch the CSV:
```powershell
curl -o jobs.csv "http://127.0.0.1:8000/api/download?token=<token>"
```

### 6. Direct Curl (Skip HTML)
```powershell
curl -F "resume=@C:/path/to/resume.pdf" -F "title=Data Engineer" -F "location=New York, NY" -F "distance=25" http://127.0.0.1:8000/api/prepare
```

### 7. Error Codes
- 400: Validation (missing / bad distance / unsupported file / size >5MB)
- 401: Adzuna auth failure
- 429: Local rate limit (12 prepare calls / 60s) or upstream 429
- 502: Upstream Adzuna error (server or invalid JSON)
- 503: Network issue contacting Adzuna
- 404 (download): Token expired or unknown

### 8. Token Lifecycle
Download tokens expire after ~10 minutes or when memory prunes older entries.

### 9. Deployment Notes
GitHub Pages alone cannot host the backend. To go online:
1. Deploy FastAPI (Fly.io / Render / Railway / Azure). Set secrets.
2. Host or modify the static `index.html` to point `fetch`/form action at your deployed base URL.
3. Enforce HTTPS; never expose credentials client-side.

### 10. Future Enhancements
- Front-end auto download + progress indicator
- Component score columns (semantic vs skill)
- Fallback provider & multi-source merge
- Better per-IP rate limiting & structured logging output

Quick checklist:
- [ ] Virtualenv active
- [ ] Dependencies installed
- [ ] ADZUNA creds set
- [ ] Uvicorn running
- [ ] Resume uploaded & token received
- [ ] CSV downloaded
