# Changelog

All notable changes to this project will be documented in this file.

The format roughly follows Keep a Changelog and Semantic Versioning.

## [Unreleased]
### Added
- Packaging metadata (pyproject.toml) with console scripts.
- Public package API exposing JobDB and JobPosting.

## [0.2.0] - 2025-09-16
### Added
- Streaming CSV export mode to reduce memory footprint.
- Compensation & benefit normalization (currency conversion + canonical benefit mapping).
- Redaction (configurable regex-based PII masking) with tests.
- ToS compliance gating (explicit opt-in required for automated collection).
- Property-based tests for skill extraction invariants (Hypothesis).
- Branch coverage uplift tests (dedupe similarity path, anomaly no-warning, redaction disabled, compliance default).
- Fuzz resume parser test with synthetic randomized inputs.
- Architecture diagram (`docs/architecture.md`).
- Migration playbook (`docs/migration_playbook.md`).

### Changed
- README expanded with architecture link and schema change guidance.

### Internal / Tooling
- Added packaging/versioning and release prep groundwork for future tags.

## [0.1.0] - 2025-09-16
### Added
- Initial packaged version including scoring, exporting, enrichment, dedupe, streaming export, normalization, redaction, compliance gating, and property-based tests.
