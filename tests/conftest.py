from hypothesis import settings, HealthCheck

# Suppress health checks that are noisy in CI for our fuzz-heavy test
settings.register_profile(
	"ci",
	suppress_health_check=[
		HealthCheck.function_scoped_fixture,
		HealthCheck.too_slow,
	],
)
settings.load_profile("ci")
