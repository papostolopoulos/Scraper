from __future__ import annotations
from pathlib import Path
import pandas as pd
import json
import yaml
import os
import csv
from .db import JobDB
from .comp_norm import load_comp_config, load_benefit_mappings, convert_salary, map_benefits
from .redaction import load_redaction_config, redact_fields
from typing import Dict, Any, Iterable, Optional

# Updated export columns for jobs_full (removed offered_salary_currency, added component scores & matched_skills)
EXPORT_COLUMNS = [
    'job_id','title','company_name','company_name_normalized','location','location_normalized','work_mode','posted_at','employment_type','seniority_level',
    'offered_salary_min','offered_salary_max','offered_salary_currency','offered_salary_min_usd','offered_salary_max_usd','benefits','benefits_normalized',
    'skill_score','semantic_score','score_total','matched_skills','status','apply_url','geocode_lat','geocode_lon'
]

class Exporter:
    """Export job data.

    Streaming mode (enabled via env SCRAPER_STREAM_EXPORT=1 or stream=True) writes CSVs row-by-row
    to minimize memory usage and skips building large in-memory DataFrames & Excel workbooks.
    Outputs in streaming mode: jobs_full.csv, jobs_shortlist.csv, jobs_explanations.csv.
    Non-streaming mode retains previous behavior including Excel artifacts.
    """

    EXPLANATION_COLUMNS = [
        'job_id','title','company_name','company_name_normalized','score_total','skill_score','semantic_score',
        'recency_score','seniority_component','matched_skills','base_extracted','resume_overlap','overlap_added',
        'semantic_added','rationale_text','weights_snapshot','thresholds_snapshot','status','apply_url'
    ]

    def __init__(self, db: JobDB, export_dir: Path, stream: Optional[bool] = None, redact: Optional[bool] = None):
        self.db = db
        self.export_dir = export_dir
        self.export_dir.mkdir(parents=True, exist_ok=True)
        if stream is None:
            env_v = os.getenv('SCRAPER_STREAM_EXPORT', '').lower()
            self.stream = env_v in ('1','true','yes','on')
        else:
            self.stream = bool(stream)
        if redact is None:
            env_r = os.getenv('SCRAPER_REDACT_EXPORT')
            self.redact = env_r.lower() in ('1','true','yes','on') if env_r is not None else None  # None means defer to config default
        else:
            self.redact = bool(redact)

    def export_all(self):
        jobs = [j for j in self.db.fetch_all() if j.status != 'duplicate']
        if not jobs:
            return None

        # Load snapshots once
        weights_path = self.export_dir.parent.parent / 'config' / 'weights.yml'
        matching_path = self.export_dir.parent.parent / 'config' / 'matching.yml'
        weights_data = {}
        matching_data = {}
        try:
            if weights_path.exists():
                with open(weights_path, 'r', encoding='utf-8') as f:
                    weights_data = yaml.safe_load(f) or {}
            if matching_path.exists():
                with open(matching_path, 'r', encoding='utf-8') as f:
                    matching_data = yaml.safe_load(f) or {}
        except Exception:
            pass
    if self.stream:
            return self._export_streaming(jobs, weights_data, matching_data)
        return self._export_non_streaming(jobs, weights_data, matching_data)

    # -------- Non streaming (original) --------
    def _export_non_streaming(self, jobs, weights_data, matching_data):
        rows = []
        rationale_rows = []
        unmatched_resp_rows = []
        for j in jobs:
            rows.append(self._job_row(j))
            br = j.score_breakdown or {}
            sm = j.skills_meta or {}
            rationale_rows.append(self._rationale_row(j, br, sm, weights_data, matching_data))
            unmatched_resp_rows.extend(self._unmatched_rows(j, sm))
        df = pd.DataFrame(rows)
        if 'job_id' in df.columns:
            df['job_id'] = df['job_id'].astype(str)
        for col in EXPORT_COLUMNS:
            if col not in df.columns:
                df[col] = None
        df = df[EXPORT_COLUMNS]
        full_path = self.export_dir / 'jobs_full.xlsx'
        df.to_excel(full_path, index=False)
        csv_path = self.export_dir / 'jobs_full.csv'
        df.to_csv(csv_path, index=False)
        shortlist = df[(df['score_total'].fillna(0) >= 0.68) | (df['status'].isin(['shortlisted','applied']))]
        shortlist_path = self.export_dir / 'jobs_shortlist.csv'
        shortlist.to_csv(shortlist_path, index=False)
        rationale_path = self.export_dir / 'jobs_rationale.xlsx'
        explanations_csv = self.export_dir / 'jobs_explanations.csv'
        if rationale_rows:
            with pd.ExcelWriter(rationale_path, engine='openpyxl') as writer:
                pd.DataFrame(rationale_rows).to_excel(writer, sheet_name='rationale', index=False)
                if unmatched_resp_rows:
                    pd.DataFrame(unmatched_resp_rows).to_excel(writer, sheet_name='unmatched_responsibilities', index=False)
            expl_df = pd.DataFrame(rationale_rows, columns=self.EXPLANATION_COLUMNS)
            expl_df.to_csv(explanations_csv, index=False)
        return {'full': full_path, 'full_csv': csv_path, 'shortlist': shortlist_path, 'rationale': rationale_path, 'explanations_csv': explanations_csv if rationale_rows else None}

    # -------- Streaming mode --------
    def _export_streaming(self, jobs, weights_data, matching_data):
        full_csv_path = self.export_dir / 'jobs_full.csv'
        shortlist_csv_path = self.export_dir / 'jobs_shortlist.csv'
        explanations_csv_path = self.export_dir / 'jobs_explanations.csv'

        with open(full_csv_path, 'w', newline='', encoding='utf-8') as full_f, \
             open(shortlist_csv_path, 'w', newline='', encoding='utf-8') as short_f, \
             open(explanations_csv_path, 'w', newline='', encoding='utf-8') as expl_f:
            full_writer = csv.DictWriter(full_f, fieldnames=EXPORT_COLUMNS)
            shortlist_writer = csv.DictWriter(short_f, fieldnames=EXPORT_COLUMNS)
            explanation_writer = csv.DictWriter(expl_f, fieldnames=self.EXPLANATION_COLUMNS)
            full_writer.writeheader()
            shortlist_writer.writeheader()
            explanation_writer.writeheader()
            for j in jobs:
                row = self._job_row(j)
                full_writer.writerow(row)
                # shortlist condition
                score_total = row.get('score_total') or 0
                if score_total >= 0.68 or row.get('status') in ('shortlisted','applied'):
                    shortlist_writer.writerow(row)
                # explanation row
                br = j.score_breakdown or {}
                sm = j.skills_meta or {}
                explanation_writer.writerow(self._rationale_row(j, br, sm, weights_data, matching_data))

        # Return only CSV artifacts in streaming mode
        return {'full': None, 'full_csv': full_csv_path, 'shortlist': shortlist_csv_path, 'rationale': None, 'explanations_csv': explanations_csv_path}

    # -------- Helpers --------
    def _job_row(self, j):
        # Lazy-load comp/benefit config once per process (cached on instance)
        if not hasattr(self, '_comp_cfg'):
            root = self.export_dir.parent.parent
            self._comp_cfg = load_comp_config(root)
            self._benefit_map = load_benefit_mappings(root)
        min_usd, max_usd = convert_salary(j.offered_salary_min, j.offered_salary_max, getattr(j, 'offered_salary_currency', None), 'yearly', self._comp_cfg)
        benefits_norm = map_benefits(j.benefits, self._benefit_map) if j.benefits else []
    record = {
            'job_id': str(j.job_id) if j.job_id is not None else '',
            'title': j.title,
            'company_name': j.company_name,
            'company_name_normalized': j.company_name_normalized,
            'location': j.location,
            'location_normalized': j.location_normalized,
            'work_mode': j.work_mode,
            'posted_at': j.posted_at.isoformat() if getattr(j, 'posted_at', None) else None,
            'employment_type': j.employment_type,
            'seniority_level': j.seniority_level,
            'offered_salary_min': j.offered_salary_min,
            'offered_salary_max': j.offered_salary_max,
            'offered_salary_currency': getattr(j, 'offered_salary_currency', None),
            'offered_salary_min_usd': min_usd,
            'offered_salary_max_usd': max_usd,
            'benefits': ", ".join(j.benefits) if j.benefits else None,
            'benefits_normalized': ", ".join(benefits_norm) if benefits_norm else None,
            'skill_score': (j.score_breakdown or {}).get('skill'),
            'semantic_score': (j.score_breakdown or {}).get('semantic'),
            'score_total': j.score_total,
            'matched_skills': ", ".join(j.skills_extracted) if j.skills_extracted else None,
            'status': j.status,
            'apply_url': j.apply_url or self._fallback_apply_url(j),
            'geocode_lat': getattr(j, 'geocode_lat', None),
            'geocode_lon': getattr(j, 'geocode_lon', None),
        }
        # Redaction (lazy load config once)
        if not hasattr(self, '_redaction_cfg'):
            root = self.export_dir.parent.parent
            self._redaction_cfg = load_redaction_config(root)
            # If user explicitly passed redact True/False override config enabled
            if self.redact is not None:
                self._redaction_cfg['enabled'] = self.redact
        if self._redaction_cfg.get('enabled'):
            redact_fields(record, ['title','company_name','location','matched_skills','apply_url'], self._redaction_cfg)
        return record

    def _rationale_row(self, j, br, sm, weights_data, matching_data):
        return {
            'job_id': j.job_id,
            'title': j.title,
            'company_name': j.company_name,
            'company_name_normalized': j.company_name_normalized,
            'score_total': j.score_total,
            'skill_score': br.get('skill'),
            'semantic_score': br.get('semantic'),
            'recency_score': br.get('recency'),
            'seniority_component': br.get('seniority_component'),
            'matched_skills': ", ".join(j.skills_extracted) if j.skills_extracted else None,
            'base_extracted': ", ".join(sm.get('base_extracted', [])[:40]) or None,
            'resume_overlap': ", ".join(sm.get('resume_overlap', [])[:40]) or None,
            'overlap_added': ", ".join(s.get('skill') for s in sm.get('overlap_added', []) if s.get('skill')) or None,
            'semantic_added': ", ".join(s.get('skill') for s in sm.get('semantic_added', []) if s.get('skill')) or None,
            'rationale_text': self._build_rationale_text(j, br, sm),
            'weights_snapshot': json.dumps(weights_data.get('weights', {})) if weights_data else None,
            'thresholds_snapshot': json.dumps(weights_data.get('thresholds', {})) if weights_data else None,
            'matching_snapshot': json.dumps(matching_data) if matching_data else None,
            'status': j.status,
            'apply_url': j.apply_url,
        }

    def _unmatched_rows(self, j, sm):
        rows = []
        unmatched = []
        if sm.get('responsibilities_all'):
            matched_resp = set(r.get('source_sentence') for r in sm.get('overlap_added', []) if r.get('source_sentence')) | set(r.get('source_sentence') for r in sm.get('semantic_added', []) if r.get('source_sentence'))
            for resp in sm.get('responsibilities_all', [])[:200]:
                if resp not in matched_resp:
                    unmatched.append(resp)
        for resp in unmatched:
            rows.append({'job_id': j.job_id, 'title': j.title, 'company_name': j.company_name, 'unmatched_responsibility': resp})
        return rows

    def _build_rationale_text(self, job, breakdown, meta):
        try:
            parts = []
            skill_v = breakdown.get('skill')
            sem_v = breakdown.get('semantic')
            rec_v = breakdown.get('recency')
            sen_v = breakdown.get('seniority_component')
            if skill_v is not None:
                parts.append(f"Skill match {skill_v:.2f}")
            if sem_v is not None:
                parts.append(f"Contextual similarity {sem_v:.2f}")
            if rec_v is not None:
                parts.append(f"Recency {rec_v:.2f}")
            if sen_v is not None:
                parts.append(f"Seniority adj {sen_v:.2f}")
            # Skill provenance summary
            provenance_bits = []
            if meta.get('resume_overlap'):
                provenance_bits.append(f"resume:{len(meta['resume_overlap'])}")
            if meta.get('overlap_added'):
                provenance_bits.append(f"resp_overlap:{len(meta['overlap_added'])}")
            if meta.get('semantic_added'):
                provenance_bits.append(f"semantic_resp:{len(meta['semantic_added'])}")
            if provenance_bits:
                parts.append('prov=' + ','.join(provenance_bits))
            top_skills = (job.skills_extracted or [])[:5]
            if top_skills:
                parts.append('key=' + '/'.join(top_skills))
            return " | ".join(parts)
        except Exception:
            return None

    def _fallback_apply_url(self, job):
        # Construct a LinkedIn job view URL if missing; job_id expected format numeric or string with digits
        try:
            jid_part = ''.join(ch for ch in job.job_id if ch.isdigit()) or job.job_id
            return f"https://www.linkedin.com/jobs/view/{jid_part}" if jid_part else None
        except Exception:
            return None
