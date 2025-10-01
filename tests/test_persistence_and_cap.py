import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from scraper.web.server import app, JOBS, _persist_job, JobRun


client = TestClient(app)


def test_persisted_job_get_fallback(tmp_path):
	# Persist a completed job to disk, clear in-memory JOBS, and ensure GET returns it
	job_id = uuid.uuid4().hex
	jr = JobRun(job_id=job_id, created=datetime.now(timezone.utc))
	jr.status = 'done'
	jr.count = 5
	jr.limit = 10
	jr.token = 'tok123'
	jr.timings = {'fetch_sec': 0.1, 'scoring_sec': 0.2, 'total_sec': 0.3}
	_persist_job(jr)
	JOBS.clear()
	r = client.get(f'/api/jobs/{job_id}')
	assert r.status_code == 200
	data = r.json()
	assert data['status'] == 'done'
	assert data['count'] == 5
	assert data['limit'] == 10
	assert data['token'] == 'tok123'


def test_hard_job_cap_enforced(tmp_path, monkeypatch):
	# Create a DB with many jobs and ensure cap via score_all reduces rows
	from scraper.jobminer.db import JobDB
	from scraper.jobminer.models import JobPosting
	from scraper.jobminer.pipeline import score_all

	monkeypatch.setenv('JOBMINER_HARD_JOB_CAP', '3')
	db_path = tmp_path / 'db.sqlite'
	db = JobDB(db_path)
	jobs = [
		JobPosting(job_id=f'src:{i}', title='T', company_name='C', description_raw='desc', description_clean='desc')
		for i in range(10)
	]
	db.upsert_jobs(jobs)
	# Minimal resume/seed files
	resume = tmp_path / 'resume.txt'; resume.write_text('python\n')
	seed = tmp_path / 'seed.txt'; seed.write_text('python\n')
	score_all(db, resume, seed, write_summary=False, max_workers=1)
	assert len(db.fetch_all()) == 3

