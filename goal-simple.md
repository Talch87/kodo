# Goal: Implement Metrics Utility Module

Implement a metrics utility module for Kodo:

1. **Create `kodo/utils/metrics.py`** with:
   - `MetricsCollector` class to track execution metrics
   - Methods: `start_timer()`, `end_timer()`, `record_metric()`, `get_summary()`
   - Support tracking: duration, API calls, tokens used, success/failure counts

2. **Create comprehensive tests** in `tests/test_metrics.py`:
   - Test metric recording and retrieval
   - Test timer functionality
   - Test summary generation
   - Achieve >90% code coverage

3. **Commit to main** with clear commit message

Success criteria:
- Module exists and is importable
- All tests pass
- Code is well-documented
- Changes are committed
