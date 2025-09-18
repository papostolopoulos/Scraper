from __future__ import annotations
"""Generate a simple static HTML dashboard from daily snapshot history.

Reads scraper/data/daily_snapshots/history.jsonl and emits
scraper/data/dashboard/index.html with inline JS and basic line charts (no external deps).

Usage (PowerShell):
  python scraper/scripts/generate_dashboard.py
  python scraper/scripts/generate_dashboard.py --history path/to/history.jsonl --out path/to/index.html
"""
import argparse
import json
import os
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

def compute_highlights(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    last = rows[-1]
    # Find previous with non-null comparable values (optional)
    prev = rows[-2] if len(rows) > 1 else None
    def delta(cur, prev):
        try:
            if cur is None or prev is None:
                return None
            return cur - prev
        except Exception:
            return None
    hl = {
        'date': (last.get('timestamp_utc') or '').split('T')[0],
        'jobs_total': last.get('jobs_total'),
        'avg_score': last.get('avg_score'),
        'skills_per_job': last.get('skills_per_job'),
        'd_jobs_total': delta(last.get('jobs_total'), prev.get('jobs_total') if prev else None),
        'd_avg_score': delta(last.get('avg_score'), prev.get('avg_score') if prev else None),
        'd_skills_per_job': delta(last.get('skills_per_job'), prev.get('skills_per_job') if prev else None),
    }
    return hl


def render_html(series: Dict[str, Any], highlights: Dict[str, Any] | None = None, weekly_link: str | None = None) -> str:
    """Render the dashboard HTML as a plain template and substitute placeholders.

    Using a plain string avoids f-string brace conflicts with embedded JS/CSS.
    """
    data_json = json.dumps(series)
    highlights_json = json.dumps(highlights or {})
    updated = datetime.utcnow().isoformat() + "Z"
    weekly_html = (
        f'<a id="weekly_link" href="{weekly_link}" target="_blank">View weekly summary</a>'
        if weekly_link else ""
    )

    html = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Job Miner Dashboard</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }
    .chart { margin: 28px 0; }
    .row { display: flex; gap: 28px; flex-wrap: wrap; }
    .card { border: 1px solid #e3e3e3; border-radius: 8px; padding: 16px; flex: 1 1 360px; }
    h1 { margin: 0 0 12px; }
    h2 { margin: 0 0 12px; font-size: 16px; color: #333; }
    .meta { color: #666; font-size: 12px; }
    canvas { width: 100%; height: 220px; }
    .legend { margin: 6px 0 0; font-size: 12px; color: #555; display: flex; align-items: center; gap: 8px; }
    .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    .highlights { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; }
    .kv { font-size: 14px; }
    .kv .k { display:block; color:#666; font-size:12px; }
    .kv .v { font-weight:600; font-size:18px; }
    #tooltip { position: fixed; background: rgba(0,0,0,0.8); color:#fff; padding:6px 8px; border-radius:4px; font-size:12px; pointer-events:none; opacity:0; transition: opacity 0.1s; z-index: 10; }
  </style>
  </head>
<body>
  <h1>Job Miner Dashboard</h1>
  <div class="meta">Updated: __UPDATED__</div>
  <div class="row">
    <div class="card">
      <h2>Latest Highlights</h2>
      <div id="highlights" class="highlights"></div>
      <div style="margin-top:8px">__WEEKLY_HTML__</div>
    </div>
  </div>
  <div class="row">
    <div class="card">
      <h2>Jobs total</h2>
      <div class="legend"><span class="dot" style="background:#3b82f6"></span><span>Jobs total</span></div>
      <canvas id="chart_jobs" width="800" height="240"></canvas>
    </div>
    <div class="card">
      <h2>Average score</h2>
      <div class="legend"><span class="dot" style="background:#10b981"></span><span>Average score</span></div>
      <canvas id="chart_score" width="800" height="240"></canvas>
    </div>
    <div class="card">
      <h2>Skills per job</h2>
      <div class="legend"><span class="dot" style="background:#f59e0b"></span><span>Skills per job</span></div>
      <canvas id="chart_skills" width="800" height="240"></canvas>
    </div>
  </div>
  <script>
    const SERIES = __DATA_JSON__;
    const HIGHLIGHTS = __HIGHLIGHTS_JSON__;
    const tooltip = document.createElement('div');
    tooltip.id = 'tooltip';
    document.body.appendChild(tooltip);

    function setTooltip(x, y, text) {
      tooltip.style.left = (x + 12) + 'px';
      tooltip.style.top = (y + 12) + 'px';
      tooltip.textContent = text;
      tooltip.style.opacity = '1';
    }
    function hideTooltip() { tooltip.style.opacity = '0'; }

    function drawLine(canvasId, labels, values, color, fillMissing=null) {
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
      function x(i) { return left + (pw * (i / Math.max(1, labels.length-1))); }
      function y(v) { const rng = (vmax - vmin) || 1; return bottom - ((v - vmin) / rng) * ph; }
      // grid lines
      ctx.strokeStyle = '#eee'; ctx.lineWidth = 1; ctx.setLineDash([4,4]);
      for (let g=0; g<=4; g++) {
        const gy = top + g * (ph/4);
        ctx.beginPath(); ctx.moveTo(left, gy); ctx.lineTo(right, gy); ctx.stroke();
      }
      ctx.setLineDash([]);
      // series
      ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
      let started=false;
      const points = [];
      for (let i=0; i<labels.length; i++) {
        const v = values[i];
        if (v==null) continue;
        const px = x(i), py = y(v);
        points.push({ x: px, y: py, v, label: labels[i], i });
        if (!started) { ctx.moveTo(px, py); started=true; } else { ctx.lineTo(px, py); }
      }
      ctx.stroke();
      // labels (sparse)
      ctx.fillStyle = '#666'; ctx.font = '11px system-ui, sans-serif';
      const step = Math.max(1, Math.floor(labels.length/6));
      for (let i=0; i<labels.length; i+=step) {
        const px = x(i);
        ctx.save(); ctx.translate(px, h-18); ctx.rotate(-0.5);
        ctx.fillText(labels[i], 0, 0); ctx.restore();
      }
      // interactivity: simple tooltip on nearest point
      const R = 6; // hover radius in px
      canvas.onmousemove = (ev) => {
        const rect = canvas.getBoundingClientRect();
        const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
        let best = null, bd = 1e9;
        for (const p of points) {
          const dx = p.x - mx, dy = p.y - my; const d2 = dx*dx + dy*dy;
          if (d2 < bd) { bd = d2; best = p; }
        }
        if (best && Math.sqrt(bd) <= R) {
          setTooltip(ev.clientX, ev.clientY, `${best.label}: ${best.v}`);
        } else hideTooltip();
      };
      canvas.onmouseleave = hideTooltip;
    }
    drawLine('chart_jobs', SERIES.labels, SERIES.jobs_total, '#3b82f6');
    drawLine('chart_score', SERIES.labels, SERIES.avg_score, '#10b981');
    drawLine('chart_skills', SERIES.labels, SERIES.skills_per_job, '#f59e0b');

    // populate highlights
    function fmtDelta(d) {
      if (d == null) return '';
      const s = (d >= 0 ? '+' : '') + (typeof d === 'number' && d.toFixed ? d.toFixed(2) : d);
      return ` (${s})`;
    }
    if (HIGHLIGHTS && Object.keys(HIGHLIGHTS).length) {
      const el = document.getElementById('highlights');
      const items = [
        {k: 'Date', v: HIGHLIGHTS.date || ''},
        {k: 'Jobs total', v: HIGHLIGHTS.jobs_total, d: HIGHLIGHTS.d_jobs_total},
        {k: 'Avg score', v: HIGHLIGHTS.avg_score, d: HIGHLIGHTS.d_avg_score},
        {k: 'Skills per job', v: HIGHLIGHTS.skills_per_job, d: HIGHLIGHTS.d_skills_per_job},
      ];
      for (const it of items) {
        const div = document.createElement('div'); div.className = 'kv';
        const k = document.createElement('span'); k.className='k'; k.textContent = it.k; div.appendChild(k);
        const v = document.createElement('span'); v.className='v'; v.textContent = (it.v==null?'-':it.v); div.appendChild(v);
        if (it.d!=null) { const d = document.createElement('span'); d.className='d'; d.style.color = (it.d>=0?'#10b981':'#ef4444'); d.textContent = fmtDelta(it.d); div.appendChild(d); }
        el.appendChild(div);
      }
    }
  </script>
</body>
</html>
"""

    return (
        html
        .replace("__UPDATED__", updated)
        .replace("__WEEKLY_HTML__", weekly_html)
        .replace("__DATA_JSON__", data_json)
        .replace("__HIGHLIGHTS_JSON__", highlights_json)
    )


def main():
    ap = argparse.ArgumentParser(description='Generate a static HTML dashboard from daily snapshots.')
    ap.add_argument('--history', default='scraper/data/daily_snapshots/history.jsonl')
    ap.add_argument('--out', default='scraper/data/dashboard/index.html')
    ap.add_argument('--weekly', default='scraper/data/daily_snapshots/weekly_summary.md', help='Path to weekly summary markdown (optional link)')
    args = ap.parse_args()

    rows = load_history(Path(args.history))
    series = prepare_series(rows)
    highlights = compute_highlights(rows)
    out_path = Path(args.out)
    # compute weekly link relative to output
    weekly_link = None
    weekly_path = Path(args.weekly)
    if weekly_path.exists():
        try:
            weekly_abs = weekly_path.resolve()
            out_dir_abs = out_path.parent.resolve()
            weekly_link = os.path.relpath(weekly_abs, out_dir_abs)
        except Exception:
            weekly_link = str(weekly_path)
    html = render_html(series, highlights, weekly_link)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding='utf-8')
    print(f'Wrote dashboard to {out_path}')


if __name__ == '__main__':
    main()
