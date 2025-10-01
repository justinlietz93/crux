from crux_providers.service.benchmark import compute_stats, run_benchmark


def test_compute_stats_empty():
    stats = compute_stats([])
    if stats["count"] != 0.0:
        raise AssertionError("expected count = 0.0 for empty input")
    if stats["mean"] != 0.0:
        raise AssertionError("expected mean = 0.0 for empty input")


def test_compute_stats_basic():
    stats = compute_stats([0.1, 0.2, 0.3])
    if stats["count"] != 3.0:
        raise AssertionError("expected count = 3.0")
    if round(stats["mean"], 3) != 0.2:
        raise AssertionError("expected mean ~ 0.2")
    if round(stats["median"], 3) != 0.2:
        raise AssertionError("expected median ~ 0.2")


def test_run_benchmark_with_measure_fn():
    # Deterministic synthetic durations: 0.01, 0.02, 0.03
    values = [0.01, 0.02, 0.03]
    it = iter(values)

    def measure():
        return next(it)

    result = run_benchmark(provider="openrouter", model=None, prompt="hi", runs=3, warmups=0, measure_fn=measure)
    measured = result["measured"]
    if measured["count"] != 3.0:
        raise AssertionError("expected measured count = 3.0")
    if round(measured["mean"], 3) != 0.02:
        raise AssertionError("expected measured mean ~ 0.02")
