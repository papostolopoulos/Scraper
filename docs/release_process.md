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
   - If using GitHub Actions Release workflow, this will produce a Release with sdist/wheel assets.
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

## GitHub Releases (CI)
- The repository includes a Release workflow that can automatically publish wheels/sdists to the GitHub Release on tag push (e.g., `v0.2.1`).
- Verify at: GitHub → Releases → latest tag page; confirm assets (wheel, sdist) are attached.

### Attach Weekly Summary to a Release (optional)
- Ensure `snapshots/weekly_summary.md` exists (generate locally or let the workflow generate it).
- Re-run Actions → "Publish Release" with ref set to the target tag (e.g., `v0.2.2`).
- The workflow installs the project, generates the weekly summary, and attaches it if present.
- If not attached, check the workflow logs for the "Attach weekly summary if present" step and re-run if needed.

## Publish Weekly Summary to GitHub Pages
1. Open GitHub → Actions → “Publish Weekly Summary”.
2. Click “Run workflow” and select the appropriate time window (e.g., 7 days).
3. After it completes, verify GitHub Pages branch `gh-pages` contains updated `_site/index.md` and assets.
4. Visit the Pages site URL (from repository Settings → Pages) and check the updated weekly summary.

Short checklist:
- [ ] Run “Publish Weekly Summary” (or wait for Monday schedule)
- [ ] Verify `gh-pages` updated
- [ ] Open Pages URL to confirm content

Troubleshooting Pages publish:
- If `_site/index.md` didn’t change, confirm snapshots exist and the workflow ran on the intended branch.
- Re-run the workflow or manually trigger after updating snapshots.

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
