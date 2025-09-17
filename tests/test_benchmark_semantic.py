from scraper.scripts.benchmark_semantic import benchmark


def test_benchmark_smoke(monkeypatch):
    metrics, path = benchmark(limit=0)  # limit=0 => no slice effect; still processes all or none
    # Keys existence
    for k in [
        'total_jobs','sampled_jobs','heuristic_time_s','semantic_time_s','avg_skills_heuristic',
        'avg_skills_semantic','avg_added_semantic','threshold','bigrams','max_new','speed_ratio']:
        assert k in metrics
    assert path.exists()