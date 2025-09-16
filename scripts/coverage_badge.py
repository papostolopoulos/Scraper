#!/usr/bin/env python
"""Generate a simple Shields.io style JSON badge from coverage.xml.
Usage: python scripts/coverage_badge.py coverage.xml coverage_badge.json
"""
from __future__ import annotations
import sys, xml.etree.ElementTree as ET, json

def main(inp: str, out: str):
    try:
        tree = ET.parse(inp)
    except Exception as e:
        print(f"Failed to parse coverage xml: {e}")
        return 1
    root = tree.getroot()
    line_rate = root.get('line-rate')
    pct = 0.0
    if line_rate:
        try:
            pct = float(line_rate) * 100.0
        except ValueError:
            pct = 0.0
    pct_int = round(pct, 1)
    # color thresholds
    if pct_int >= 90:
        color = 'brightgreen'
    elif pct_int >= 80:
        color = 'green'
    elif pct_int >= 70:
        color = 'yellowgreen'
    elif pct_int >= 60:
        color = 'yellow'
    elif pct_int >= 50:
        color = 'orange'
    else:
        color = 'red'
    badge = {
        "schemaVersion": 1,
        "label": "coverage",
        "message": f"{pct_int}%",
        "color": color,
    }
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(badge, f, ensure_ascii=False, indent=2)
    print(f"Wrote badge {out}: {badge['message']}")
    return 0

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: coverage_badge.py <coverage.xml> <out.json>")
        sys.exit(1)
    sys.exit(main(sys.argv[1], sys.argv[2]))