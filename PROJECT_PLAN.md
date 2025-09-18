# Job Miner Project Plan

## 1. Objective & Reliability Criteria
**Objective (Updated Sep 18, 2025):** Deliver a simple web experience where a user can upload a resume, enter job search criteria, and download a CSV (capped at 100 roles) ranked against their skills. Preserve determinism, transparency, and ToS compliance while focusing on an MVP path to value.

**What Success Looks Like:**
- You can run one command to collect (or ingest) jobs, score them, and export structured outputs (Excel / CSV) any day with consistent runtime and without manual cleanup.
- The results are reproducible: the same inputs (resume + job set + config) yield the same scores (aside from timestamp/recency components).
- The system is transparent: each score is explainable (skills matched, weighting, bonuses/penalties).
- Failures are visible early: CI, pre-commit hooks, and metrics surface issues before they corrupt data.
- Adding new jobs or updating resume content does not require code edits—just files/config.

**Reliability & Data Quality Factors (Essential):**
1. Input Integrity: Resume parsing, job description capture, and skill extraction must not silently drop content.
2. Deterministic Scoring Logic: Pure functions (aside from time-based decay) ensure confidence in ranking repeatability.
3. Caching Correctness: Skill & resume caches accelerate runs without serving stale or mismatched data (hash/version guard + size/age pruning).
4. Schema Stability & Migration: DB schema versioning guards against silent field drift; migrations are tested.
5. Performance Envelope: Import + standard run finishes within an acceptable window (< a few minutes) so iteration remains fast.
6. Test Coverage & Fast Feedback: Core pipelines, cache logic, migration, and performance constraints are tested; slow/external tests isolated.
7. Observability: Run summary metrics (timings, cache hit/miss) enable trend tracking and early anomaly detection.
8. Operational Safety: Login detection avoids brittle scraping loops when session expires; environment flags allow safe dry runs.
9. Security/Compliance: Minimizing automated interaction with third-party sites; respecting Terms of Service; isolating optional collector.
10. Developer Hygiene: Linting, typing, pre-commit, reruns for flaky tests, and CI coverage to reduce regressions.

## 2. Completed Tasks (Plain Language & Why They Matter)
| Area | What Was Done (Plain Language) | Why It Was Important |
|------|--------------------------------|----------------------|
| Resume Understanding | We parse the resume once and store structured sections and skills. | Avoids re-reading and speeds up scoring; consistent skill base. |
| Skill Memory | We keep a growing file of previously analyzed job descriptions and their extracted skills. | Saves time on repeated runs and avoids reprocessing unchanged postings. |
| Scoring Pipeline | A script puts everything together: loads jobs, analyzes skills overlap, produces a score, and exports files. | Gives a single repeatable action to get ranked jobs. |
| Export Outputs | Creates Excel and CSV outputs, including a focused shortlist. | Easy sharing and filtering without touching code. |
| Database Foundation | Stores job postings with a version tag so we can evolve structure safely. | Keeps historical data and prevents format confusion. |
| Schema Version Tracking | We record the database layout version and test it. | Early warning if we forget to migrate after changing fields. |
| Caching (Resume) | The processed resume is cached with a content fingerprint. | Changes to the resume automatically rebuild; unchanged keeps things fast. |
| Caching (Skills) | Each job description’s skills are cached with limits. | Speeds up repeat runs and bounds disk use. |
| Cache Trimming Policy | We enforce size and entry limits, plus a manual trim script. | Prevents uncontrolled growth and keeps performance stable. |
| Environment Flags | Simple switches to disable logs/events or rebuild caches. | Control noise and troubleshoot faster. |
| Run Summary Metrics | After a run we write a small JSON with timing + cache stats. | Enables tracking performance over time. |
| Login Detection | Detects when a session is on a login page and avoids useless scraping. | Prevents misleading empty data and wasted time. |
| Import Performance Optimization | Deferred heavy modules so startup is quick. | Faster feedback loops = more iteration and less frustration. |
| Slow Test Marking | Labeled long tests so day‑to‑day runs skip them by default. | Keeps most test runs fast. |
| Test Speedups | Stubbed expensive PDF parsing and reduced waits in tests. | Lower friction running tests often. |
| Test Timeout Guard | Added a timeout per test to avoid hangs. | Prevents stalled CI pipelines. |
| Coverage Reporting (XML + HTML) | Collects pnd publishes code coverage reports. | Shows what code is untested; supports quality tracking. |
| Coverage Badge JSON | Generates a badge artifact summarizing coverage %. | Visual progress indicator. |
| Pre-commit Hooks | Automatic checks (style, type, quick tests) before commits. | Catches issues early; consistent codebase. |
| Flaky Test Reruns (Local + CI) | Automatic reruns for marked flaky tests only. | Reduces noise while not hiding real failures. |
| Limited Rerun Logic | CI reruns only tests labeled flaky; others fail fast. | Keeps signal high while tolerating known instability. |
| CI Workflow Hardening | Matrix Python versions, security audit, artifacts, caching. | Cross-version confidence and supply chain vigilance. |
| Fast Test Script | One command to run quick subset of tests. | Encourages frequent verification. |

| External Source Adapter (Indeed) | Added a non-scraping loader for local Indeed JSON with normalization and ID namespacing. | Enables safe multi-source ingestion and offline testing without live collection (ToS‑friendly). |
| Semantic Config Externalization | Introduced `config/semantic.yml` with environment overrides and a `max_new` cap. | Easier tuning, deterministic runs, and safe bounds on enrichment additions. |
| Semantic Benchmark & Caching | Added benchmark script, seed token caching, and optional embedding of metrics into run summary. | Visibility into enrichment overhead and trend tracking; faster repeated runs. |

## 3. Remaining Tasks (To Reach “Complete” Definition)
Grouped by theme (plain language first):

A. Data Quality & Enrichment
- Consider embedding-based skill expansion (optional) with toggle + tests (semantic TF‑IDF enrichment exists today).

B. User Experience & Transparency
- (No pending items — explanations, weighting config, and outcome CLI are implemented.)

C. Reliability & Monitoring
- Implement daily snapshot automation (small, consistent dataset) and persist key metrics for trend analysis.
- Optional lightweight health dashboard (local HTML or Markdown generation).

D. Scaling & Performance
- (No pending items — parallel extraction and streaming export are implemented.)

E. Data Governance & Safety
- (No pending items — redaction and ToS compliance gate are implemented.)

F. Test & Quality Gaps
- (No pending items — property-based/fuzz tests and branch coverage uplift are implemented.)

G. Documentation & Onboarding
- (No pending items — Quickstart, architecture diagram, and migration playbook are published.)

H. Release & Distribution
- Finalize 1.0.0 release and polish changelog as features land.

I. Optional Stretch Features
- Additional sources (beyond Indeed) via plug‑in interface.
- Resume A/B comparison (two resumes, scoring deltas).
- Skill gap recommender (top missing skills per cluster of high‑interest jobs).

## 3a. MVP Definition & Priority Order (Re-scoped for Web UI)
**MVP Goal:** A local web page (can reuse/extend the existing Job Miner page) that lets a user:
- Upload a resume (PDF/DOCX); resume is parsed to extract skills/keywords.
- Enter search inputs: Job title (required), Location (required), Distance from location (required), Date posted (optional), Work mode (optional), Employment type (optional), Salary expectation (optional), Benefits (optional via radio buttons).
- Run a compliant search (API-based or local adapters), score results against the resume skills, and download a CSV with up to 100 positions.

Notes on compliance: Automated scraping of LinkedIn search results violates LinkedIn’s Terms of Service. For the MVP, prioritize compliant data sources (e.g., API partners such as Adzuna, Jora, Jooble, or SERP providers that are ToS-compliant). If LinkedIn is required later, gate it behind an explicit compliance flag and require manual sign-in/session with clear user consent—still risky and not recommended for automated collection.

**MVP Must-Haves (execution order):**
1. Minimal web UI form
	- Single HTML page served locally with: file upload for resume; inputs for Job title (required), Location (required), Distance (required); optional fields for Date posted, Work mode, Employment type, Salary, Benefits (radio).
	- Basic client-side validation for required fields.
2. Resume parsing and skills extraction
	- Reuse existing resume parser and skill extraction; return a normalized skill list.
3. Compliant job source adapter
	- Integrate one API-based job source (configurable keys); map filters (title, location, distance, date posted, work mode/remote, employment type, salary).
	- Normalize fields into our internal job schema.
4. Scoring + limit + dedupe
	- Reuse scoring; cap results to 100; remove near-duplicates (by title/company/location similarity).
5. CSV export and download
	- Provide a "Download results" button that streams the CSV to the browser.
6. Operational guardrails
	- ToS compliance flag; clear error messages and input validation; simple logging.
7. Quickstart
	- README section: how to run locally; where to configure API keys; how to use the page end-to-end.

**Post-MVP (High Value Next):**
- Multiple sources with fallback/merge; richer filters; improved ranking signals.
- Saved configuration presets.
- UI polish and accessibility.
- Optional: gated LinkedIn session-based fetcher (manual login; compliance flag) — de-prioritized.

**Stretch Goals:**
- User accounts (email + password) to store uploaded resume for faster analysis next time.
- Daily email digests of new jobs per user — requires a persistent DB, background scheduler/worker, and email infrastructure.

## 3b. Progress Tracking (Est vs Actual)
| Task | Category | Est Hours | Actual Hours | Status | Notes |
|------|----------|----------:|-------------:|--------|-------|
| Weighting config + validation | MVP | 5 | 1.5 | Done | JSON/YAML schema + test |
| Explanation export | MVP | 2 | 1 | Done | Add columns / separate CSV |
| Outcome tracking CLI | MVP | 5 | 2 | Done | Status history + funnel metrics + CLI stats/history |
| Historical run log + anomaly check | MVP | 3 | 1.5 | Done | Run JSONL + avg score & skills rate drop detection |
| Quickstart docs | MVP | 2 | 0.5 | Done | Added 5‑minute Quickstart in README |
| Semantic enrichment toggle | Post-MVP | 7 | 1 | Done | Unified toggle precedence + tests |
| Dedupe refinement | Post-MVP | 4 | 1 | Done | Added fuzzy title + Jaccard near-duplicate pass |
| Parallel extraction | Post-MVP | 7 | 2 | Done | ThreadPool + deterministic equivalence tests |
| Benefit/comp normalization | Later | 5 | 1 | Done | Currency conversion + benefit mapping + tests |
| Batch export optimization | Later | 3 | 1 | Done | Streaming CSV mode + parity tests |
| Redaction option | Governance | 3 | 1 | Done | Configurable regex masking + tests |
| ToS compliance flag | Governance | 2 | 1 | Done | Gating via flag/env/config + tests |
| Property-based tests | Quality | 6 | 1 | Done | Hypothesis invariants for skill extraction |
| Fuzz resume parser | Quality | 1 | 0.5 | Done | Hypothesis synthetic text + monkeypatched extract_text |
| Branch coverage uplift | Quality | 4 | 1 | Done | Added targeted tests (dedupe similarity off, anomaly no-warning, redaction disabled, compliance default deny) |
| Architecture diagram | Docs | 3 | 1 | Done | Mermaid diagram in docs/architecture.md + README link |
| Migration playbook | Docs | 1 | 0.5 | Done | docs/migration_playbook.md + README link |
| Packaging + versioning | Release | 5 | 1 | Done | pyproject + console scripts + changelog |
| Release 0.2.0 prep | Release | 2 | 0.5 | Done | Changelog 0.2.0, version bump, release & migration docs |
| Multi-source ingestion | Stretch | 6 | 2 | Done | Plugin framework + mock source + ingest script + tests |
| Release automation (GH Actions) | Release | 2 | 0.5 | Done | Tag-triggered build + release notes extraction |
| Semantic enrichment refinement | Post-MVP | 5 | 1 | Done | TF-IDF cosine expansion + deterministic ordering + tests |

> Actual Hours: Will be filled when each task completes; variance tracked (+/- %).

## 3c. Daily Sample Extraction Plan
- Add script to run a small controlled extraction (or simulate if no live scraping) each day.
- Store snapshot: job count, average score, top 5 titles, cache hit %, run duration.
- Keep last N (e.g., 14) snapshots in `data/daily_snapshots/` for trend review.
- Optional later: generate a weekly Markdown summary.

## 3d. Variance Tracking
For each completed task: `variance = (Actual - Est) / Est`. If variance > +40% twice in a row, revisit estimation assumptions.

## 3e. Focus Guardrails
- Never start more than 2 in-progress tasks simultaneously (limit WIP).
- MVP tasks (Web UI + compliant search + CSV download) trump other features until MVP is done.
- Stretch features cannot begin before Milestone 2 complete unless explicitly re-prioritized.

## 4. Timeline of Completed Work (Approximate Sequence)
1. Core data models, DB foundation, basic scoring & export.
2. Resume parsing + skill extraction + caching layers.
3. Pipeline orchestration script & run summary metrics.
4. Login detection & operational environment flags.
5. Cache policies (size/age + trimming script).
6. Schema versioning & migration tests.
7. Performance + import time optimization.
8. Mark slow tests & add test speed fixtures.
9. Add timeouts & initial coverage reporting.
10. CI hardening (matrix, security audit, artifacts).
11. Coverage HTML + badge artifact.
12. Pre-commit hooks & fast test script.
13. Flaky rerun support & limited rerun logic in CI.

## 5. Effort Estimate to Reach Completion
(Assuming one experienced engineer with context; adjust if parallel work possible.)

| Work Area | Est. Hours |
|-----------|-----------:|
| Semantic skill enrichment + tests | 6–8 |
| Benefit/compensation normalization  | 4–6 |
| Deduplication refinement | 3–5 |
| Explanations & weighting config validation | 5–7 |
| Outcome tracking + CLI funnel metrics | 4–6 |
| Metrics anomaly detection + historical log | 3–4 |
| Parallel extraction + concurrency guard | 6–8 |
| Batch export optimization | 3–4 |
| Anonymization / redaction option | 2–3 |
| ToS compliance flag & guardrail | 1–2 |
| Property-based + fuzz tests | 5–7 |
| Branch coverage increases | 3–4 |
| Quickstart + architecture doc | 3–4 |
| Migration playbook doc | 1–2 |
| Packaging & versioning setup + changelog | 4–5 |
| Stretch (per item, optional) | 6–12 |
| Buffer / Integration / Review | 6–8 |
| TOTAL (without stretch) | ~60–75 |

## 6. Agile Milestones & Definition of Done (DoD)

### Milestone 1: Feature Transparency & Quality Baseline (Weeks 1–2)
Scope: Explanations, weighting config validation, quickstart doc, anomaly detection log, outcome tracking CLI.
DoD:
- Running pipeline produces explanation-enriched export.
- Weight config changes validated with a failing test if invalid.
- Historical run log file grows with each run; anomaly check issues warning on threshold breach.
- CLI logs application outcomes, exporting simple funnel metrics.
- Docs updated (quickstart + explanation section).

### Milestone 2: Data Enrichment & Performance (Weeks 3–4)
Scope: Semantic skill enrichment, parallel extraction, dedupe refinement, batch export optimization.
DoD:
- Semantic enrichment toggle ON adds incremental matched skills; OFF leaves baseline identical.
- Parallel extraction reduces average extraction time vs. baseline (documented in run summary).
- Duplicate detection test passes on synthetic cluster set.
- Exports succeed with large job dataset (performance test within time budget).

### Milestone 3: Governance & Hardening (Weeks 5–6)
Scope: Redaction/anonymization, ToS flag, property-based & fuzz tests, branch coverage uplift, migration playbook.
DoD:
- Redaction flag removes sensitive tokens in export test fixture.
- Automated collection requires explicit flag; CI ensures flag absent by default.
- Property-based tests run green; fuzz test catches malformed edge cases deterministically.
- Coverage threshold raised (e.g., line >=85%).
- Migration guide present and referenced in README.

### Milestone 4: Packaging & Release Readiness (Week 7)
Scope: Packaging, versioning, changelog, final documentation polish.
DoD:
- Build produces installable wheel.
- Tagged release increments semantic version with changelog entry.
- README and architecture diagram reflect final state.
- All quality gates (lint, type, coverage, flaky policy) pass on release tag.

(Stretch features to be scheduled after core completion or in separate post-MVP epics.)

## 7. Governance & Working Agreements
- Keep flaky tests to an explicit small set; removal required once stabilized.
- No merging to main with decreased coverage or failed type/lint gates (unless documented exception).
- Every schema change requires: migration, version bump, test update, doc note.
- New feature PR must add or update at least one test.
- Weekly review of run summary trends (time, cache hit rate, extraction success).

## 8. Risks & Mitigations
| Risk | Impact | Mitigation |
|------|--------|-----------|
| Overfitting scoring weights | Skewed rankings | Validation + explanation exports + configurable weights. |
| Scraping instability | Data gaps | Login detection + optional manual import path. |
| LinkedIn ToS violations | Legal/Account risk | Prefer API-based sources; gate any LinkedIn automation behind explicit compliance flags and manual session; avoid by default. |
| Cache corruption | Inaccurate scores | Hash/version guard + tests + trim policy. |
| Test suite slowdown | Developer friction | Slow markers, fast scripts, selective reruns. |
| Silent schema drift | Runtime errors later | Version table + migration tests. |
| Flaky tests masking real issues | Hidden defects | Limit reruns to marked flaky only. |

## 9. Definition of Project Completion
The project is considered complete when:
- All Milestones 1–4 DoD items achieved.
- Line coverage >=85% and branch coverage tracked.
- No open P1 reliability bugs.
- Ability to process a target dataset size within agreed performance budget.
- Documentation (quickstart + architecture + migration + explanations) is current.
- Release 1.0.0 tag published with changelog.

---
Prepared: (Generated automatically)

## 10. Process Improvement Suggestions
| Area | Current State | Improvement Suggestion | Benefit |
|------|---------------|------------------------|---------|
| Daily Feedback | Manual review only | Automate daily snapshot script + store metrics | Early drift detection |
| Estimation Accuracy | Initial coarse estimates | Track variance per task in table | Better planning confidence |
| Onboarding | Long README | Add Quickstart + architecture diagram | Faster contributor ramp-up |
| Test Signal | Flaky reruns limited | Add periodic flaky audit (remove stabilized) | Keeps suite lean |
| Run Metrics | Single summary JSON | Append history + simple anomaly flags | Trend visibility |
| Code Ownership | Broad | Mark OWNER in module headers (optional) | Accountability / review focus |
| Release Readiness | Manual steps | Add release GitHub Action (tag -> build + changelog) | Consistency |

<!-- NEXT_STEP_START -->
### Suggested Next Step
Build the MVP web flow: serve a minimal HTML form (resume upload + required search fields), wire a compliant job source adapter, and return a downloadable CSV (max 100). Document local run steps and API key config.
<!-- NEXT_STEP_END -->

_Maintenance Note:_ Run `python scripts/update_next_step.py` after updating the progress table to refresh this Suggested Next Step section automatically.
