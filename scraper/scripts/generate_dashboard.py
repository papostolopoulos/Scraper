from __future__ import annotations
"""Generate a simple static HTML dashboard from daily snapshot history.

Reads scraper/data/daily_snapshots/history.jsonl and emits
scraper/data/dashboard/index.html with inline JS and basic line charts (no external deps).

Usage (PowerShell):
  python scraper/scripts/generate_dashboard.py
  python scraper/scripts/generate_dashboard.py --history path\to\history.jsonl --out path\to\index.html
"""
import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


def load_history(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                # skip malformed
                pass
    # sort by timestamp if present
    def parse_ts(r):
        ts = r.get('timestamp_utc')
        try:
            return datetime.fromisoformat(ts.replace('Z','+00:00')) if ts else datetime.min
        except Exception:
            return datetime.min
    rows.sort(key=parse_ts)
    return rows


def prepare_series(rows: List[Dict[str, Any]]):
    labels: List[str] = []
    jobs: List[float] = []
    score: List[float] = []
    skills: List[float] = []
    for r in rows:
        ts = r.get('timestamp_utc') or ''
        labels.append(ts.split('T')[0] if 'T' in ts else ts)
        jobs.append(float(r.get('jobs_total', 0) or 0))
        score_val = r.get('avg_score')
        score.append(float(score_val) if score_val is not None else None)
        skills_val = r.get('skills_per_job')
        skills.append(float(skills_val) if skills_val is not None else None)
    return {
        'labels': labels,
        'jobs_total': jobs,
        'avg_score': score,
        'skills_per_job': skills,
    }


def render_html(series: Dict[str, Any]) -> str:
    # Inline minimal JS for line drawing on <canvas>
    data_json = json.dumps(series)
    html = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Job Miner Dashboard</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }}
    .chart {{ margin: 28px 0; }}
    .row {{ display: flex; gap: 28px; flex-wrap: wrap; }}
    .card {{ border: 1px solid #e3e3e3; border-radius: 8px; padding: 16px; flex: 1 1 360px; }}
    h1 {{ margin: 0 0 12px; }}
    h2 {{ margin: 0 0 12px; font-size: 16px; color: #333; }}
    .meta {{ color: #666; font-size: 12px; }}
    canvas {{ width: 100%; height: 220px; }}
  </style>
</head>
<body>
  <h1>Job Miner Dashboard</h1>
  <div class=\"meta\">Updated: {datetime.utcnow().isoformat()}Z</div>
  <div class=\"row\">
    <div class=\"card\">
      <h2>Jobs total</h2>
      <canvas id=\"chart_jobs\" width=\"800\" height=\"240\"></canvas>
    </div>
    <div class=\"card\">
      <h2>Average score</h2>
      <canvas id=\"chart_score\" width=\"800\" height=\"240\"></canvas>
    </div>
    <div class=\"card\">
      <h2>Skills per job</h2>
      <canvas id=\"chart_skills\" width=\"800\" height=\"240\"></canvas>
    </div>
  </div>
  <script>
    const SERIES = {data_json};
    function drawLine(canvasId, labels, values, color, fillMissing=null) {{
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const w = canvas.width, h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      ctx.strokeStyle = '#ddd'; ctx.lineWidth = 1;
      // axes
      ctx.beginPath(); ctx.moveTo(40, 10); ctx.lineTo(40, h-30); ctx.lineTo(w-10, h-30); ctx.stroke();
      // prepare data
      const vals = values.map(v => (v==null && fillMissing!=null) ? fillMissing : v).filter(v => v!=null);
      if (vals.length === 0) return;
      const vmax = Math.max(...vals), vmin = Math.min(...vals);
      const left = 40, right = w-20, top = 10, bottom = h-30;
      const pw = right - left, ph = bottom - top;
      function x(i) {{ return left + (pw * (i / Math.max(1, labels.length-1))); }}
      function y(v) {{ const rng = (vmax - vmin) || 1; return bottom - ((v - vmin) / rng) * ph; }}
      // grid lines
      ctx.strokeStyle = '#eee'; ctx.lineWidth = 1; ctx.setLineDash([4,4]);
      for (let g=0; g<=4; g++) {{
        const gy = top + g * (ph/4);
        ctx.beginPath(); ctx.moveTo(left, gy); ctx.lineTo(right, gy); ctx.stroke();
      }}
      ctx.setLineDash([]);
      // series
      ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
      let started=false;
      for (let i=0; i<labels.length; i++) {{
        const v = values[i];
        if (v==null) continue;
        const px = x(i), py = y(v);
        if (!started) {{ ctx.moveTo(px, py); started=true; }} else {{ ctx.lineTo(px, py); }}
      }}
      ctx.stroke();
      // labels (sparse)
      ctx.fillStyle = '#666'; ctx.font = '11px system-ui, sans-serif';
      const step = Math.max(1, Math.floor(labels.length/6));
      for (let i=0; i<labels.length; i+=step) {{
        const px = x(i);
        ctx.save(); ctx.translate(px, h-18); ctx.rotate(-0.5);
        ctx.fillText(labels[i], 0, 0); ctx.restore();
      }}
    }}
    drawLine('chart_jobs', SERIES.labels, SERIES.jobs_total, '#3b82f6');
    drawLine('chart_score', SERIES.labels, SERIES.avg_score, '#10b981');
    drawLine('chart_skills', SERIES.labels, SERIES.skills_per_job, '#f59e0b');
  </script>
</body>
</html>
"""
    return html


def main():
    ap = argparse.ArgumentParser(description='Generate a static HTML dashboard from daily snapshots.')
    ap.add_argument('--history', default='scraper/data/daily_snapshots/history.jsonl')
    ap.add_argument('--out', default='scraper/data/dashboard/index.html')
    args = ap.parse_args()

    rows = load_history(Path(args.history))
    series = prepare_series(rows)
    html = render_html(series)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding='utf-8')
    print(f'Wrote dashboard to {out_path}')


if __name__ == '__main__':
    main()
