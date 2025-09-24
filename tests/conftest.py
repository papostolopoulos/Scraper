from hypothesis import settings, HealthCheck

# Suppress function-scoped fixture health check for compatibility with tests using monkeypatch + Hypothesis
settings.register_profile("ci", suppress_health_check=[HealthCheck.function_scoped_fixture])
settings.load_profile("ci")
