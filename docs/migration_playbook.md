# Migration Playbook

A concise, repeatable procedure for evolving the SQLite schema without corrupting data or breaking cached assumptions.

## Principles
- Backwards-safe first: add columns as NULLABLE; populate in a later pass.
- Idempotent scripts: running twice produces same state.
- Version gate: schema modifications occur only if `meta.schema_version < TARGET`.
- Data preservation: use table rename + selective column copy for destructive changes.
- Test before merge: migration test loads previous fixture DB, runs init, asserts new columns & data integrity.

## Versioning
`settings.SCHEMA_VERSION` holds the integer schema version. Bump it when:
- Adding/removing a column
- Changing column semantic meaning (type widening, unit change)
- Adjusting indexes materially

Do NOT bump for:
- Adding an index (non-breaking)
- Data backfill scripts not changing schema shape

## Migration Types
| Type | Preferred Approach |
|------|--------------------|
| Add column | `ALTER TABLE jobs ADD COLUMN new_col TYPE` (NULL default) |
| Remove column | Recreate table: rename → create new schema → copy selected columns → drop old |
| Rename column | Add new, copy data, (optionally) remove old in next version |
| Change type | Add new column with correct type, backfill, switch consumers, drop old in future version |

## Step-by-Step Checklist
1. Design Change
   - Define purpose & usage of new/changed field(s).
   - Decide if nullable; avoid NOT NULL without default for existing rows.
2. Update Models
   - Add field to `models.JobPosting` with default `None` if optional.
3. Update DB Schema Constant
   - Modify `SCHEMA_SQL` if new column needed.
   - Add conditional `ALTER TABLE` blocks in `JobDB.__init__` for additive change.
4. Handle Destructive Changes (if needed)
   - Implement recreate block: rename old, create fresh, copy subset columns.
   - Include inside try/except with transaction (`BEGIN` / `ROLLBACK` on failure).
5. Bump `SCHEMA_VERSION`
   - Update in `settings.py`.
6. Write Migration Test
   - Create fixture DB representing previous version (or use dynamic creation by temporarily setting version constant).
   - Instantiate `JobDB`; assert new column present (`PRAGMA table_info`).
   - Insert row pre-migration path and ensure post-migration data persists.
7. Backfill (Optional)
   - If new column derived from existing data, write a small post-migration function or script.
8. Update Export / Scoring Logic
   - Ensure new field included where relevant (export columns, scoring adjustments, CLI).
9. Documentation
   - Add row to `PROJECT_PLAN.md` notes or CHANGELOG entry under Unreleased.
   - Update `docs/architecture.md` if data flow changes.
10. Review & Merge
   - Ensure tests (including migration test) pass and coverage not decreased.
11. Release
   - Increment version (if user-facing) and add CHANGELOG entry after merge.

## Example: Add `job_board_source`
1. Add `job_board_source: str | None = None` to `JobPosting`.
2. In `SCHEMA_SQL`, include `job_board_source TEXT` column.
3. In `JobDB.__init__`, check if absent then `ALTER TABLE jobs ADD COLUMN job_board_source TEXT`.
4. Bump `SCHEMA_VERSION` (e.g., 5 → 6).
5. Migration test asserts column exists, inserting old-style row still works.

## Smoke Test Commands
```powershell
# After pulling changes
python - <<'PY'
from scraper.jobminer.db import JobDB
from pathlib import Path
import sqlite3
# Open existing DB, ensure new column exists
with sqlite3.connect('scraper/data/db.sqlite') as c:
    cols = [r[1] for r in c.execute('PRAGMA table_info(jobs)')]
print('job_board_source' in cols)
PY
```

## Common Pitfalls
- Forgetting to bump schema version: cache or tests may use stale assumptions.
- Dropping columns without data copy: silent data loss.
- Adding NOT NULL columns without defaults: migration fails for existing rows.
- Not updating model serialization (export, UI) causing missing data downstream.

## Rollback Strategy
If migration fails in production environment:
1. Stop pipeline runs.
2. Restore last DB backup (recommend daily copies of `db.sqlite`).
3. Revert commit or fix migration script; re-run initialization.
4. Re-execute scoring/export to regenerate derived artifacts.

## Future Improvements
- Dedicated `migrations/` directory with numbered scripts.
- Automated snapshot backup prior to migration.
- CLI command `jobminer-migrate` orchestrating dry-run & apply modes.
