# Architecture Overview

This document maps the core modules, data flow, and key quality / governance controls of the Job Miner system.

## High-Level Flow

```mermaid
graph TD
    A[Resume PDF] -->|parse & cache| R[resume.py\nResumeProfile]
    SUBGRAPH_SOURCES[[Sources Plugin Layer]] --> B[Collected Jobs]
    SRC1[Source: mock] --> SUBGRAPH_SOURCES
    %% Future: Indeed / Other Boards plug-ins
    B -->|store| DB[(SQLite Jobs DB)]
    R --> S[skills.py\nExtract Skills]
    DB --> S
    S --> SEM[semantic_enrich.py\nTF-IDF Expand]
    SEM --> SC[Scoring Pipeline\n(score.py)]
    WEIGHT[weights config\nweights.yaml/json] --> SC
    SC --> DED[dedupe.py\nDeterministic + Similarity]
    DED --> ANO[anomaly.py\nRun Metrics]
    SC --> EXP[exporter.py\nExport Rows]
    COMP[comp_norm.py\nCurrency + Benefits] --> EXP
    RED[redaction.py\nPII Mask] --> EXP
    COMPL[compliance.py\nToS Gate] --> B
    EXP --> OUT1[[CSV / Excel]]
    EXP --> OUT2[[Streaming CSV]]
    ANO --> RUNLOG[(run_history.jsonl)]
```

## Module Responsibilities

- `resume.py`: Extracts structured profile (summary, expertise, responsibilities, aggregated skills) from PDF with caching keyed by file hash + seed skills.
- `skills.py`: Derives job-specific skill signals; supports semantic enrichment toggle (off = deterministic baseline).
- `score.py` (implied): Combines weighting config, matched skills, bonuses/penalties into composite score + explanation payloads.
- `dedupe.py`: Removes exact & near-duplicate job postings using canonical signature + fuzzy/Jaccard similarity pass (configurable toggle for similarity step).
- `anomaly.py`: Compares latest run metrics (avg score, skills/job) against rolling baseline and emits warnings for significant drops.
- `exporter.py`: Generates exports in memory or streaming mode; integrates compensation normalization, redaction, and explanation columns.
- `comp_norm.py`: Normalizes salaries (e.g. to USD) and maps benefits to canonical vocabulary.
- `redaction.py`: Applies configurable regex rules to sensitive fields (emails, phone numbers, etc.).
- `compliance.py`: Enforces explicit opt-in for automated collection actions (safety/net for ToS compliance).

## Data Stores & Artifacts

| Artifact | Purpose | Lifespan |
|----------|---------|----------|
| SQLite DB (jobs) | Persist raw & enriched job postings | Long-term, versioned |
| Resume cache JSON | Avoid re-parsing unchanged resume PDF | Rebuilt when hash/seed changes |
| Skill cache (per job) | Skip re-extracting unchanged JD skills | Size/age bounded |
| Run history JSONL | Trend analysis & anomaly detection | Rolling window (configurable) |
| Exports (CSV/Excel) | User-facing ranked shortlist & full dataset | Per run |
| Coverage/Reports | Quality oversight (CI artifacts) | CI retention |

## Quality & Reliability Controls

| Control | Layer | Mechanism |
|---------|-------|-----------|
| Deterministic hashing | Caching | Resume + skill caches keyed by content hash/version |
| Weight validation | Scoring | Schema + test ensures required weights and bounds |
| Property-based tests | Skills/Resume | Hypothesis invariants for extraction logic |
| Branch coverage tests | Dedupe/Anomaly/Redaction/Compliance | Edge-case branches executed |
| Redaction toggle | Governance | Config/env flag; tests ensure both paths |
| Compliance gate | Governance | Deny-by-default unless explicit opt-in |
| Anomaly detection | Monitoring | Threshold drop guard for avg score & extraction rate |
| Streaming export | Performance | Reduces memory footprint on large datasets |
| Parallel extraction | Performance | Thread pool with deterministic equivalence tests |

## Key Data Flow Notes

1. Resume parsing occurs once per session unless resume file or seed skill list changes (hash invalidation).
2. Each job posting flows through skill extraction, scoring, then duplicate filtering before export.
3. Explanations (matched skills, weighting contributions) are embedded in export rows for transparency.
4. Compensation normalization & benefit mapping augment rows before optional redaction.
5. Anomaly module consumes run summary metrics (written at end of pipeline) and appends to the historical log.
6. Governance flags (redaction, compliance) gate side-effects but never compromise core scoring determinism.

## Extensibility Points

- Additional ingestion sources: implement a source adapter writing into the DB schema then reuse pipeline.
- New scoring factors: add to weight config schema + scoring function; update explanation export.
- Alternate embedding model / semantic layer: wrap behind enrichment toggle to preserve baseline determinism.
- Additional governance checks: add new module parallel to `compliance.py` and invoke early in pipeline.

## Future Enhancements (Diagram Impact)

- Architecture may expand with a `plugins/` directory for ingestion adapters.
- A lightweight `dashboard.py` could visualize `run_history.jsonl` trends.
- Add `migrations/` folder if schema changes become frequent (documented process already planned).

---
Generated: automated assistant (Mermaid diagram viewable on GitHub / compatible renderers).
