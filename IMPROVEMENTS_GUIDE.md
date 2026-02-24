# Kodo Improvements Implementation Guide

This document guides implementation of the improvements outlined in `ANALYSIS.md`.

## Files Added

### 1. `kodo/errors.py` ✅ COMPLETE
Structured error types and retry policies.

**Key classes:**
- `AgentError` — Structured representation of failures
- `ErrorType` — Classification (timeout, auth, network, etc.)
- `RetryPolicy` — Exponential backoff retry strategy
- `_classify_exception()` — Automatically classify exceptions

**Usage:**
```python
try:
    result = agent.run(goal, project_dir)
except Exception as e:
    error = AgentError.from_exception(e, context=ErrorContext(agent_name="worker"))
    if error.retriable:
        # Retry with backoff
        pass
    else:
        # Escalate
        pass
    log.emit("agent_error", error=error.to_dict())
```

### 2. `kodo/schemas.py` ✅ COMPLETE
Pydantic models for configuration validation.

**Key classes:**
- `AgentConfigSchema` — Validates individual agent configs
- `TeamConfigSchema` — Validates team.json structure
- `UserConfigSchema` — Validates ~/.kodo/config.json
- `GoalPlanSchema` — Validates goal-plan.json

**Benefits:**
- Fast feedback on config errors (at load time, not runtime)
- Self-documenting with Field descriptions
- Type-safe config handling

**Integration points:**
- `team_config.py`: Update `load_team_config()` to validate with `TeamConfigSchema`
- `user_config.py`: Update `get_user_default()` to validate with `UserConfigSchema`
- `intake.py`: Update goal plan generation to use `GoalPlanSchema`

---

## Implementation Roadmap

### Phase 1: Error Handling (2-3 hours)

**File: `kodo/agent.py`**
```python
# Add import
from kodo.errors import AgentError, ErrorContext, NO_RETRY, DEFAULT_RETRY

# Update Agent.run() exception handling:
try:
    query_result = self.session.query(goal, project_dir, max_turns=self.max_turns)
except FuturesTimeoutError:
    error = AgentError(
        error_type=ErrorType.TIMEOUT,
        message=f"Agent timed out after {self.timeout_s}s",
        retriable=True,
    )
    # Log and return
except Exception as e:
    error = AgentError.from_exception(e, context=ErrorContext(agent_name=label))
    # Log and return
```

**File: `kodo/sessions/base.py`**
```python
# Add error context to QueryResult
@dataclass
class QueryResult:
    # ... existing fields ...
    error: AgentError | None = None  # Structured error if failed

# When session encounters error:
error = AgentError.from_exception(exc)
result = QueryResult(text=str(exc), is_error=True, error=error)
```

**Tests to add:**
- `tests/test_error_handling.py` — Test error classification, retry logic
- `tests/test_agent_recovery.py` — Test agent recovery from errors

### Phase 2: Config Validation (2-3 hours)

**File: `kodo/team_config.py`**
```python
from kodo.schemas import validate_team_config

def load_team_config(path: Path) -> TeamConfigSchema:
    """Load and validate team config."""
    data = json.loads(path.read_text())
    return validate_team_config(data)  # Raises on invalid config
```

**File: `kodo/user_config.py`**
```python
from kodo.schemas import validate_user_config

def get_user_default() -> UserConfigSchema:
    """Load and validate user config."""
    config_path = Path.home() / ".kodo" / "config.json"
    if config_path.exists():
        data = json.loads(config_path.read_text())
        return validate_user_config(data)
    return UserConfigSchema()  # Defaults
```

**Tests to add:**
- `tests/config/test_validation.py` — Test invalid configs are rejected
- `tests/config/test_schemas.py` — Test schema parsing

### Phase 3: Session Retry Logic (3-4 hours)

**File: `kodo/sessions/base.py`**
```python
class Session:
    def __init__(self, ..., retry_policy: RetryPolicy = DEFAULT_RETRY):
        self.retry_policy = retry_policy
    
    def query_with_retry(self, prompt: str, project_dir: Path, **kwargs) -> QueryResult:
        """Execute query with automatic retry on retriable errors."""
        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                return self.query(prompt, project_dir, **kwargs)
            except Exception as e:
                error = AgentError.from_exception(e)
                if not self.retry_policy.should_retry(error, attempt):
                    raise  # Don't retry
                
                delay = self.retry_policy.get_delay_s(attempt)
                log.emit("session_retry", attempt=attempt + 1, delay_s=delay)
                time.sleep(delay)
```

**File: `kodo/agent.py`**
```python
# In Agent.run(), use query_with_retry if available:
try:
    if hasattr(self.session, 'query_with_retry'):
        query_result = self.session.query_with_retry(goal, project_dir)
    else:
        query_result = self.session.query(goal, project_dir)
except ... as e:
    # Handle remaining errors
```

**Tests to add:**
- `tests/sessions/test_retry_logic.py` — Test exponential backoff, max retries
- `tests/test_integration_runs.py` — Add retry scenarios to integration tests

### Phase 4: Context Budgeting (3 hours)

**File: `kodo/sessions/context_budget.py` (new)**
```python
@dataclass
class ContextBudget:
    """Proactive token budgeting to avoid context resets."""
    
    total_tokens: int
    reserved_for_output: float = 0.2  # Reserve 20% for output
    
    def can_fit_query(self, query_tokens: int) -> bool:
        """Check if query fits before submitting."""
        available = self.total_tokens * (1 - self.reserved_for_output)
        return query_tokens < available
    
    def forecast_after_query(self, query: str, estimated_output_ratio: float = 2.0) -> int:
        """Estimate total tokens after query."""
        # This is approximate; improve with actual token counting
        pass
```

**File: `kodo/sessions/base.py`**
```python
class Session:
    def __init__(self, ..., context_window_tokens: int = 128000):
        self.budget = ContextBudget(total_tokens=context_window_tokens)
    
    def query(self, prompt: str, project_dir: Path, **kwargs) -> QueryResult:
        """Query with proactive budget checking."""
        estimated_tokens = len(prompt) // 4  # Very rough estimate
        
        if not self.budget.can_fit_query(estimated_tokens):
            log.emit("context_budget_exceeded_proactive")
            self.reset()  # Reset BEFORE making request
        
        # ... make query ...
        # After query, update budget
```

**Tests to add:**
- `tests/sessions/test_context_budget.py` — Test budget calculations and reset decisions

### Phase 5: Decision Logging (2 hours)

**File: `kodo/orchestrators/base.py`**
```python
@dataclass
class OrchestratorDecision:
    agent_name: str
    task: str
    reasoning: str
    alternatives: list[str]
    confidence: float
    feedback: str = ""  # Filled in post-run

class CycleResult:
    decisions: list[OrchestratorDecision] = field(default_factory=list)
```

**File: `kodo/orchestrators/api.py`**
```python
# When making a tool call decision:
decision = OrchestratorDecision(
    agent_name=agent_name,
    task=task_summary,
    reasoning=model_reasoning,  # Extract from LLM output
    alternatives=other_agents_considered,
    confidence=decision_confidence_score,
)
result.decisions.append(decision)
log.emit("orchestrator_decision", decision=asdict(decision))
```

**Tests to add:**
- `tests/orchestrators/test_decision_logging.py` — Verify decisions are logged

### Phase 6: Parallel Execution Support (4-5 hours)

**File: `kodo/orchestrators/parallel.py` (new)**
```python
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess

def run_agents_parallel(
    agents: dict[str, Agent],
    tasks: dict[str, str],
    project_dir: Path,
    parallel_group: int = 1,
) -> dict[str, AgentResult]:
    """Run multiple agents concurrently with git worktree isolation.
    
    Each agent gets its own worktree copy of the project to avoid conflicts.
    """
    # For parallel_group > 0, create worktrees for isolation
    worktrees = {}
    if parallel_group > 0:
        main_tree = project_dir
        for agent_name in agents:
            wt = main_tree / f".git-worktree-{agent_name}"
            subprocess.run(["git", "worktree", "add", str(wt)], cwd=main_tree)
            worktrees[agent_name] = wt
    
    # Run agents in parallel
    results = {}
    with ThreadPoolExecutor(max_workers=len(agents)) as executor:
        futures = {
            executor.submit(
                agents[name].run,
                tasks[name],
                worktrees.get(name, project_dir),
            ): name
            for name in agents
        }
        for future in concurrent.futures.as_completed(futures):
            agent_name = futures[future]
            results[agent_name] = future.result()
    
    # Cleanup worktrees
    for agent_name, wt in worktrees.items():
        subprocess.run(["git", "worktree", "remove", str(wt)], cwd=project_dir)
    
    return results
```

**Integration point:** `kodo/orchestrators/base.py`
```python
def dispatch_parallel_group(self, agents, tasks, project_dir):
    """Dispatch agents to run in parallel."""
    from kodo.orchestrators.parallel import run_agents_parallel
    return run_agents_parallel(agents, tasks, project_dir)
```

**Tests to add:**
- `tests/orchestrators/test_parallel_execution.py` — Test concurrent agent execution
- `tests/orchestrators/test_git_worktree_isolation.py` — Test isolation behavior

---

## Integration Checklist

### Before merging:
- [ ] All new modules import correctly
- [ ] Existing tests pass: `pytest tests/ -m "not live"`
- [ ] No regressions in `test_integration_runs.py`
- [ ] New tests pass: `pytest tests/ -k "error or retry or config or budget or decision or parallel"`
- [ ] Type checking passes: `mypy kodo/` (if configured)
- [ ] Update `CHANGELOG.md` with improvements
- [ ] Update docstrings and README if public APIs changed

### Docs to update:
- [ ] `docs/error-handling.md` — New error handling guide
- [ ] `docs/debugging.md` — How to read structured error logs
- [ ] `docs/team-config-schema.md` — Formal schema reference
- [ ] `README.md` — Mention improved error handling

---

## Testing Strategy

### Run tests at each phase:
```bash
# Unit tests for new modules
pytest tests/ -k "error" -v
pytest tests/ -k "schema" -v
pytest tests/ -k "retry" -v

# Integration tests (no live backends)
pytest tests/test_integration_runs.py -v

# Full suite
pytest tests/ -m "not live" -v

# With live backends (optional)
pytest tests/ -m live -v
```

### Performance regression testing:
```bash
# Before changes: benchmark existing runs
time kodo --goal "test goal" --cycles 1 ./test-project

# After changes: ensure no performance degradation
time kodo --goal "test goal" --cycles 1 ./test-project
```

---

## Migration Guide for Existing Projects

For existing Kodo users, these changes are **backward compatible**:
- Existing configs still work (schemas are permissive)
- Error handling is opt-in (old code still works)
- Retry logic is transparent (users don't see complexity)

**No action needed** for end users. The improvements work automatically.

---

## Questions & Debugging

If a phase gets stuck:
1. Check the existing test suite for patterns
2. Look at similar code in the codebase (e.g., if adding retry logic, check how timeouts are handled)
3. Ask in discussion/issues for clarification on expected behavior

---

**Timeline:** 20-25 hours total effort spread over 4-6 weeks
**Recommended pace:** 1 phase per week
