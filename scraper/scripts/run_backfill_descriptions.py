from __future__ import annotations
"""Backfill missing descriptions & company for existing jobs by navigating to their detail pages."""
import sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from jobminer.db import JobDB
from jobminer.models import JobPosting
from jobminer.collector import extract_job_from_panel

DETAIL_URL = "https://www.linkedin.com/jobs/view/{job_id}/"

LIMIT_PER_RUN = 30


def backfill(limit: int = LIMIT_PER_RUN, headless: bool = False):
    db = JobDB()
    jobs = [j for j in db.fetch_all() if (not j.description_raw) or j.company_name == 'Unknown']
    jobs = jobs[:limit]
    if not jobs:
        print("No jobs need backfill")
        return 0, 0
    updated = 0
    profile_dir = './data/browser_profile'
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch_persistent_context(profile_dir, headless=headless)
        except Exception as e:
            print(f"Failed to launch browser: {e}")
            return 0, len(jobs)
        page = browser.new_page()
        for j in jobs:
            url = DETAIL_URL.format(job_id=j.job_id)
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=45000)
                time.sleep(1.2)
                panel = extract_job_from_panel(page)
                changed = False
                if panel.get('description_raw') and not j.description_raw:
                    j.description_raw = panel['description_raw']
                    j.description_clean = panel['description_clean']
                    changed = True
                if j.company_name == 'Unknown' and panel.get('company_name'):
                    j.company_name = panel['company_name']
                    changed = True
                # Update if we previously had no skills (skills extraction happens later in scoring pipeline)
                if changed:
                    db.upsert_jobs([j])
                    updated += 1
                    print(f"Updated {j.job_id} -> company={j.company_name} desc_len={len(j.description_raw or '')}")
            except PlaywrightTimeoutError:
                print(f"Timeout fetching {url}")
            except Exception as e:
                print(f"Error {url}: {e}")
        browser.close()
    return updated, len(jobs)

if __name__ == '__main__':
    upd, considered = backfill()
    print(f"Backfill updated {upd} / {considered}")
