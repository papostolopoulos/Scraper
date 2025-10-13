#!/usr/bin/env python
"""Dynamic coverage gate: require current total >= recorded baseline + 2% (unless baseline missing).

Baseline file: scripts/.coverage_baseline (single float percent). If absent, create it from current.
Usage: invoked in CI after tests produce coverage.xml.
"""
from __future__ import annotations
import sys, re, pathlib
import xml.etree.ElementTree as ET

COV_XML = pathlib.Path('coverage.xml')
BASE = pathlib.Path('scripts/.coverage_baseline')
DELTA = 3.0  # required improvement margin (ratchet tightened)

def current_coverage() -> float:
    if not COV_XML.exists():
        print('coverage.xml missing', file=sys.stderr)
        return 0.0
    tree = ET.parse(COV_XML)
    root = tree.getroot()
    # Cobertura format: <coverage line-rate="0.85" branch-rate="0.72" ...>
    line_rate = root.attrib.get('line-rate')
    if not line_rate:
        return 0.0
    return float(line_rate) * 100.0


def main():
    cur = current_coverage()
    if not BASE.exists():
        print(f'Baseline not found. Creating baseline at {cur:.2f}%')
        BASE.write_text(f'{cur:.2f}', encoding='utf-8')
        return 0
    try:
        base_val = float(BASE.read_text().strip())
    except Exception:
        base_val = 0.0
    required = base_val + DELTA
    print(f'Baseline: {base_val:.2f}%  Current: {cur:.2f}%  Required: {required:.2f}%')
    if cur + 1e-9 < required:  # allow tiny float tolerance
        # Message reflects current DELTA requirement
        print(f'Coverage gate not met (needs +{DELTA:.0f}% over baseline).', file=sys.stderr)
        return 1
    # Update baseline if improved meaningfully (>0.5%) to ratchet upwards gradually
    if cur - base_val >= 0.5:
        BASE.write_text(f'{cur:.2f}', encoding='utf-8')
        print(f'Baseline raised to {cur:.2f}%')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
