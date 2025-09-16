#!/usr/bin/env python
"""Update the Suggested Next Step section in PROJECT_PLAN.md.

Logic:
1. Parse the progress table under '## 3b. Progress Tracking' to find first task with Status 'Pending'.
2. If none Pending, select any with Status 'In Progress'. If none, mark as 'All MVP tasks complete or waiting manual update'.
3. Write between <!-- NEXT_STEP_START --> and <!-- NEXT_STEP_END --> markers.

Run: python scripts/update_next_step.py
"""
from __future__ import annotations
import re
from pathlib import Path

PLAN_PATH = Path('PROJECT_PLAN.md')

TABLE_SECTION_HEADER = '## 3b. Progress Tracking'
NEXT_START = '<!-- NEXT_STEP_START -->'
NEXT_END = '<!-- NEXT_STEP_END -->'

def parse_table(lines: list[str]) -> list[dict]:
    rows: list[dict] = []
    header_idx = None
    for i,l in enumerate(lines):
        if l.strip().startswith('| Task |'):
            header_idx = i
            break
    if header_idx is None:
        return rows
    for l in lines[header_idx+2:]:  # skip header + separator
        if not l.strip().startswith('|'):
            break
        cols = [c.strip() for c in l.strip().strip('|').split('|')]
        if len(cols) < 6:
            continue
        rows.append({
            'task': cols[0],
            'category': cols[1],
            'est': cols[2],
            'actual': cols[3],
            'status': cols[4].lower(),
            'notes': cols[5],
        })
    return rows

def choose_next(rows: list[dict]) -> str:
    # Prioritize MVP pending tasks first
    mvp_pending = [r for r in rows if r['category'].lower() == 'mvp' and r['status'] == 'pending']
    if mvp_pending:
        r = mvp_pending[0]
        return f"Start Task: {r['task']} (category {r['category']}, est {r['est']}h)."
    # Then any pending
    any_pending = [r for r in rows if r['status'] == 'pending']
    if any_pending:
        r = any_pending[0]
        return f"Start Task: {r['task']} (category {r['category']}, est {r['est']}h)."
    # In progress tasks (resume / finish)
    in_prog = [r for r in rows if 'progress' in r['status']]
    if in_prog:
        r = in_prog[0]
        return f"Continue Task: {r['task']} (in progress)."
    return "All listed tasks complete or awaiting new backlog items."

def update_next_section(text: str, suggestion: str) -> str:
    pattern = re.compile(re.escape(NEXT_START) + r".*?" + re.escape(NEXT_END), re.DOTALL)
    replacement = f"{NEXT_START}\n### Suggested Next Step\n{suggestion}\n{NEXT_END}"
    if pattern.search(text):
        return pattern.sub(replacement, text)
    # Append if markers missing
    return text.rstrip() + '\n\n' + replacement + '\n'

def main():
    if not PLAN_PATH.exists():
        raise SystemExit('PROJECT_PLAN.md not found')
    text = PLAN_PATH.read_text(encoding='utf-8')
    lines = text.splitlines()
    if TABLE_SECTION_HEADER not in text:
        raise SystemExit('Progress tracking section not found')
    rows = parse_table(lines)
    suggestion = choose_next(rows)
    new_text = update_next_section(text, suggestion)
    if new_text != text:
        PLAN_PATH.write_text(new_text, encoding='utf-8')
        print('Updated Suggested Next Step ->', suggestion)
    else:
        print('No changes made (section already up to date).')

if __name__ == '__main__':
    main()