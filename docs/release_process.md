# Release Process

Lightweight procedure for publishing a new version (manual tagging workflow).

## Preconditions
- All tests green (unit, property, fuzz, branch coverage) locally.
- Coverage threshold met (>= target defined in CI policies).
- CHANGELOG has an entry for the new version with date.
- `pyproject.toml` version bumped and matches intended tag.

## Steps
1. Final Review
   - Run: `python -m pytest -q` (fast run) then optionally with coverage.
   - Verify no uncommitted changes: `git status`.
2. Update Unreleased Section
   - Move items to new version section if not already.
3. Commit & Tag
   - Commit message: `release: vX.Y.Z`.
   - Create tag: `git tag -a vX.Y.Z -m "Release X.Y.Z"`.
4. Push
   - `git push origin main --tags`.
5. Build Artifact (optional pre-push if using CI to publish)
   - `python -m build` (add `build` to dev deps if needed) or `python -m pip install build`.
   - Wheel appears in `dist/`.
6. (Optional) Test Install Locally
   - In a fresh venv: `pip install dist/jobminer-X.Y.Z-py3-none-any.whl`.
   - Run a console script: `jobminer-export --help`.
7. Post-Release Bump (Optional)
   - Increment to next dev version (e.g., `0.3.0-dev`) and add placeholder Unreleased section.
8. Announce
   - Summarize key features/perf improvements.

## Versioning Policy
- PATCH: Bug fixes & non-breaking internal tweaks.
- MINOR: New backward-compatible features (current release example: 0.2.0 adds normalization, redaction, fuzz tests, etc.).
- MAJOR: Backward-incompatible schema or API changes.

## Quick Commands (PowerShell)
```powershell
python -m pytest -q
python -m pip install build
python -m build
Get-FileHash dist/*.whl
```

## Checklist
- [ ] Tests green
- [ ] Version bumped
- [ ] Changelog updated
- [ ] Tag created
- [ ] Wheel built & (optionally) test-installed
- [ ] Docs (architecture, migration) current

---
Generated: automated assistant.
