from scraper.jobminer.skills import extract_skills


def test_semantic_enrichment_adds_missing_seed():
    description = "We build distributed systems in Python and orchestrate containers with Kubernetes and Helm charts for deployment. Observability with Prometheus and Grafana."
    seed = ["Python", "Kubernetes", "Grafana", "Prometheus", "Helm Charts", "Distributed Systems", "Observability Pipeline"]
    base = extract_skills(description, seed, semantic=False)
    enriched = extract_skills(description, seed, semantic=True)
    # Base should contain some core direct matches
    assert "Python" in base and "Kubernetes" in base
    # Enriched should be a superset (no removals)
    assert set(base).issubset(set(enriched))
    # Expect semantic-only addition (e.g., phrase not heuristically matched)
    semantic_only = set(enriched) - set(base)
    assert semantic_only  # at least one new
    # Deterministic ordering: base prefix unchanged
    assert enriched[:len(base)] == base


def test_semantic_no_duplicates():
    description = "Python Python Python data pipelines airflow orchestration"
    seed = ["Python", "Data Pipelines", "Airflow", "airflow"]
    enriched = extract_skills(description, seed, semantic=True)
    assert len(enriched) == len(set(enriched))


def test_semantic_disabled_path():
    description = "Rust blockchain consensus"  # exotic terms maybe not matched
    seed = ["Rust", "Blockchain", "Consensus Algorithm"]
    base = extract_skills(description, seed, semantic=False)
    enriched = extract_skills(description, seed, semantic=True)
    # semantic True may add "Consensus Algorithm" if similarity passes
    assert set(base).issubset(set(enriched))