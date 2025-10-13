from pathlib import Path
import json
from scraper.jobminer.anomaly import detect_anomalies, load_history
from scraper.jobminer.history import append_history


def write_runs(path: Path, avg_scores, skills_rates):
    """Helper to write multiple runs to history file"""
    for s, r in zip(avg_scores, skills_rates):
        append_history({'avg_score': s, 'skills_per_job': r, 'jobs_processed': 5}, path)


def test_anomaly_edge_case_zero_baseline():
    """Test anomaly detection when baseline values are zero"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        hist = tmp_path / "hist.jsonl"
        
        # Baseline runs with zero average scores (shouldn't trigger false positives)
        write_runs(hist, [0.0, 0.0, 0.0, 0.0, 0.0, 0.5], [5.0, 5.1, 5.2, 5.0, 5.1, 5.0])
        warns = detect_anomalies(hist)
        
        # Should not trigger warning when baseline is zero
        assert not any('Average score drop' in w for w in warns)


def test_anomaly_edge_case_negative_values():
    """Test anomaly detection with negative or invalid values"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        hist = tmp_path / "hist.jsonl"
        
        # Include some negative or None values - but ensure 5 valid previous scores
        data_points = [
            {'avg_score': 0.6, 'skills_per_job': 5.0, 'jobs_processed': 5},
            {'avg_score': 0.61, 'skills_per_job': -1.0, 'jobs_processed': 5},  # negative skills_per_job
            {'avg_score': 0.59, 'skills_per_job': 5.0, 'jobs_processed': 5},
            {'avg_score': 0.60, 'skills_per_job': None, 'jobs_processed': 5},  # None skills_per_job
            {'avg_score': 0.58, 'skills_per_job': 5.1, 'jobs_processed': 5},
            {'avg_score': 0.62, 'skills_per_job': 5.2, 'jobs_processed': 5},
            {'avg_score': 0.30, 'skills_per_job': 5.0, 'jobs_processed': 5},  # This should trigger
        ]
        
        for data in data_points:
            append_history(data, hist)
        
        warns = detect_anomalies(hist)
        # Should handle None values gracefully and detect the real drop
        assert any('Average score drop' in w for w in warns)


def test_anomaly_edge_case_insufficient_valid_data():
    """Test when there are enough entries but not enough valid values"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        hist = tmp_path / "hist.jsonl"
        
        # 7 entries but only 2 have valid avg_score values
        data_points = [
            {'avg_score': 0.6, 'skills_per_job': 5.0, 'jobs_processed': 5},
            {'avg_score': None, 'skills_per_job': 5.1, 'jobs_processed': 5},
            {'avg_score': None, 'skills_per_job': 5.2, 'jobs_processed': 5},
            {'avg_score': None, 'skills_per_job': 5.0, 'jobs_processed': 5},
            {'avg_score': None, 'skills_per_job': 5.1, 'jobs_processed': 5},
            {'avg_score': 0.61, 'skills_per_job': 5.0, 'jobs_processed': 5},
            {'avg_score': 0.30, 'skills_per_job': 5.0, 'jobs_processed': 5},
        ]
        
        for data in data_points:
            append_history(data, hist)
        
        warns = detect_anomalies(hist)
        # Should not trigger warning due to insufficient valid baseline data
        assert not any('Average score drop' in w for w in warns)


def test_anomaly_custom_parameters():
    """Test anomaly detection with custom recent_n and threshold parameters"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        hist = tmp_path / "hist.jsonl"
        
        # Create a small drop that's below default threshold but above custom threshold
        write_runs(hist, [0.60, 0.62, 0.61, 0.59, 0.60, 0.50], [5.0, 5.1, 5.2, 5.0, 5.1, 5.0])
        
        # Default threshold (35%) should not trigger
        warns_default = detect_anomalies(hist)
        assert not any('Average score drop' in w for w in warns_default)
        
        # Custom lower threshold (15%) should trigger
        warns_custom = detect_anomalies(hist, drop_threshold_pct=0.15)
        assert any('Average score drop' in w for w in warns_custom)
        
        # Custom recent_n=2 (only look at last 2 runs for baseline)
        warns_custom_n = detect_anomalies(hist, recent_n=2, drop_threshold_pct=0.15)
        assert any('Average score drop' in w for w in warns_custom_n)


def test_anomaly_malformed_history_file():
    """Test handling of malformed JSON lines in history file"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        hist = tmp_path / "hist.jsonl"
        
        # Write some valid and invalid JSON lines
        lines = [
            '{"avg_score": 0.6, "skills_per_job": 5.0, "jobs_processed": 5}',
            'invalid json line',
            '{"avg_score": 0.61, "skills_per_job": 5.1, "jobs_processed": 5}',
            '{"avg_score":}',  # malformed
            '{"avg_score": 0.59, "skills_per_job": 5.2, "jobs_processed": 5}',
            '{"avg_score": 0.60, "skills_per_job": 5.0, "jobs_processed": 5}',
            '{"avg_score": 0.58, "skills_per_job": 5.1, "jobs_processed": 5}',
            '{"avg_score": 0.30, "skills_per_job": 5.0, "jobs_processed": 5}',
        ]
        
        hist.write_text('\n'.join(lines), encoding='utf-8')
        
        warns = detect_anomalies(hist)
        # Should handle malformed lines gracefully and still detect the drop
        assert any('Average score drop' in w for w in warns)


def test_anomaly_missing_fields():
    """Test handling of entries missing required fields"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        hist = tmp_path / "hist.jsonl"
        
        # Create extra entries to ensure we have enough valid ones in the last 5
        data_points = [
            {'skills_per_job': 5.1, 'jobs_processed': 5},  # missing avg_score (early, won't affect baseline)
            {'avg_score': 0.6, 'skills_per_job': 5.0, 'jobs_processed': 5},
            {'avg_score': 0.61, 'skills_per_job': 5.1, 'jobs_processed': 5},  # Add skills_per_job
            {'avg_score': 0.59, 'skills_per_job': 5.0, 'jobs_processed': 5},
            {'avg_score': 0.60, 'skills_per_job': 5.1, 'jobs_processed': 5},
            {'avg_score': 0.62, 'skills_per_job': 5.2, 'jobs_processed': 5},
            {'avg_score': 0.58, 'skills_per_job': 5.3, 'jobs_processed': 5},
            {'avg_score': 0.30, 'skills_per_job': 2.0, 'jobs_processed': 5},  # Both drops should trigger
        ]
        
        for data in data_points:
            append_history(data, hist)
        
        warns = detect_anomalies(hist)
        # Should handle missing fields and detect drops where data exists
        assert any('Average score drop' in w for w in warns)
        assert any('Skills per job drop' in w for w in warns)


def test_anomaly_load_history_edge_cases():
    """Test load_history function edge cases"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Test with non-existent file
        non_existent = tmp_path / "nonexistent.jsonl"
        history = load_history(non_existent)
        assert history == []
        
        # Test with empty file
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("", encoding='utf-8')
        history = load_history(empty_file)
        assert history == []
        
        # Test with only whitespace
        whitespace_file = tmp_path / "whitespace.jsonl"
        whitespace_file.write_text("   \n  \n  ", encoding='utf-8')
        history = load_history(whitespace_file)
        assert history == []
        
        # Test max_lines parameter
        large_file = tmp_path / "large.jsonl"
        lines = []
        for i in range(60):
            lines.append(json.dumps({'run': i, 'avg_score': 0.5 + i * 0.01}))
        large_file.write_text('\n'.join(lines), encoding='utf-8')
        
        # Default max_lines=50 should limit results
        history = load_history(large_file)
        assert len(history) == 50
        assert history[0]['run'] == 10  # Should start from run 10 (60-50)
        
        # Custom max_lines
        history_custom = load_history(large_file, max_lines=10)
        assert len(history_custom) == 10
        assert history_custom[0]['run'] == 50  # Should start from run 50 (60-10)


def test_anomaly_boundary_conditions():
    """Test boundary conditions for anomaly detection"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        hist = tmp_path / "hist.jsonl"
        
        # Test exact threshold boundary (should not trigger)
        baseline_score = 0.60
        drop_score = baseline_score * (1 - 0.35)  # Exactly 35% drop
        write_runs(hist, [baseline_score] * 5 + [drop_score], [5.0] * 6)
        
        warns = detect_anomalies(hist)
        # Exactly at threshold should not trigger (uses > not >=)
        assert not any('Average score drop' in w for w in warns)
        
        # Test just over threshold (should trigger)
        hist2 = tmp_path / "hist2.jsonl"
        drop_score_over = baseline_score * (1 - 0.351)  # Just over 35% drop
        write_runs(hist2, [baseline_score] * 5 + [drop_score_over], [5.0] * 6)
        
        warns2 = detect_anomalies(hist2)
        assert any('Average score drop' in w for w in warns2)


def test_anomaly_very_small_values():
    """Test anomaly detection with very small baseline values"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        hist = tmp_path / "hist.jsonl"
        
        # Very small baseline values (but not zero)
        baseline = 0.001
        current = 0.0005  # 50% drop
        write_runs(hist, [baseline] * 5 + [current], [0.1] * 5 + [0.05])
        
        warns = detect_anomalies(hist)
        assert any('Average score drop' in w for w in warns)
        assert any('Skills per job drop' in w for w in warns)


import tempfile


def test_anomaly_all_metrics_combination():
    """Test anomaly detection when both avg_score and skills_per_job trigger warnings"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        hist = tmp_path / "hist.jsonl"
        
        # Both metrics drop significantly
        write_runs(hist, [0.60, 0.62, 0.61, 0.59, 0.60, 0.30], [5.0, 5.1, 5.2, 5.0, 5.1, 2.0])
        
        warns = detect_anomalies(hist)
        assert len(warns) == 2  # Both warnings should be present
        assert any('Average score drop' in w for w in warns)
        assert any('Skills per job drop' in w for w in warns)


def test_anomaly_missing_current_values():
    """Test when current run is missing the metric values"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        hist = tmp_path / "hist.jsonl"
        
        data_points = [
            {'avg_score': 0.6, 'skills_per_job': 5.0, 'jobs_processed': 5},
            {'avg_score': 0.61, 'skills_per_job': 5.1, 'jobs_processed': 5},
            {'avg_score': 0.59, 'skills_per_job': 5.2, 'jobs_processed': 5},
            {'avg_score': 0.60, 'skills_per_job': 5.0, 'jobs_processed': 5},
            {'avg_score': 0.58, 'skills_per_job': 5.1, 'jobs_processed': 5},
            {'jobs_processed': 5},  # Current run missing both metrics
        ]
        
        for data in data_points:
            append_history(data, hist)
        
        warns = detect_anomalies(hist)
        # Should not trigger warnings when current values are missing
        assert warns == []