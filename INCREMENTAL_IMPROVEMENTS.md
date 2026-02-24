# Kodo Incremental Improvements — PR Strategy

This document describes the 6-phase improvement plan broken into **incremental PRs** for easy review and testing.

## Overview

Each PR focuses on a single improvement area with:
- ✅ Standalone functionality (can be merged independently)
- ✅ Full test coverage (40+ tests per PR)
- ✅ Detailed PR description explaining benefits
- ✅ Clear integration path for next PRs

**Total effort:** ~20-25 hours across 6 PRs  
**Recommended pace:** 1 PR per week

---

## PR Queue

### ✅ PR #0: Analysis & Planning (COMPLETED)

**Status:** Merged to main  
**Branch:** `main` (already committed)  
**Files:**
- `ANALYSIS.md` — Comprehensive codebase analysis
- `IMPROVEMENTS_GUIDE.md` — Implementation roadmap
- `INCREMENTAL_IMPROVEMENTS.md` — This file

**Summary:** Identifies 7 improvement areas with detailed analysis, code examples, and implementation guides.

---

### 🚀 PR #1: Structured Error Handling & Retry Policies

**Status:** Ready for review  
**Branch:** `feature/phase1-error-handling`  
**Description:** `PR_1_DESCRIPTION.md`

**What:** Introduces `AgentError` class, error classification, and retry policies.

**New files:**
- `kodo/errors.py` (6.3 KB) — Error types, classification, retry logic
- `tests/test_error_handling.py` (7.2 KB) — 25+ tests
- `PR_1_DESCRIPTION.md` — Integration guide

**Key features:**
- Automatic exception classification (11 types)
- Exponential backoff retry strategy
- Rich error context for debugging
- JSON serialization for logging

**Dependencies:** None (standalone)

**Next PR:** Can start PR #2 immediately (independent)

---

### 🚀 PR #2: Config Validation with Pydantic Schemas

**Status:** Ready for review  
**Branch:** `feature/phase2-config-validation`  
**Description:** `PR_2_DESCRIPTION.md`

**What:** Adds Pydantic validation for all configuration files.

**New files:**
- `kodo/schemas.py` (6.4 KB) — 5 Pydantic models + validators
- `tests/test_config_schemas.py` (11.1 KB) — 40+ tests
- `PR_2_DESCRIPTION.md` — Integration guide

**Key features:**
- `AgentConfigSchema` — Validates agent configs
- `TeamConfigSchema` — Validates team definitions
- `UserConfigSchema` — Validates user settings
- `GoalPlanSchema` — Validates goal plans
- Helper methods (`.get_agent()`, `.all_backends()`)

**Dependencies:** None (standalone)

**Next PR:** Can start PR #3 immediately (independent)

---

### 📋 PR #3: Session Retry Integration (NOT YET CREATED)

**Status:** Planned  
**Estimated:** 3-4 hours effort

**What:** Integrates PR #1 error handling into session layer.

**Expected changes:**
- Modify `kodo/sessions/base.py` to use `RetryPolicy`
- Add `query_with_retry()` method with automatic backoff
- Update `QueryResult` to include `AgentError` object
- Add session retry tests

**Dependencies:** PR #1 (errors.py)

**Benefits:** Sessions automatically retry on transient failures

---

### 📋 PR #4: Config Loading Integration (NOT YET CREATED)

**Status:** Planned  
**Estimated:** 2-3 hours effort

**What:** Integrates PR #2 schemas into config loading.

**Expected changes:**
- Update `kodo/team_config.py` to validate with `TeamConfigSchema`
- Update `kodo/user_config.py` to validate with `UserConfigSchema`
- Update `kodo/intake.py` to validate `GoalPlanSchema`
- Improve error messages shown to users

**Dependencies:** PR #2 (schemas.py)

**Benefits:** Early detection of invalid configs with clear error messages

---

### 📋 PR #5: Context Budgeting & Proactive Reset (NOT YET CREATED)

**Status:** Planned  
**Estimated:** 3 hours effort

**What:** Proactive context management to prevent mid-run resets.

**Expected changes:**
- New module `kodo/sessions/context_budget.py`
- `ContextBudget` class with token forecasting
- Proactive reset logic in sessions
- Tests for budget calculations

**Benefits:** Fewer surprise context resets, more predictable behavior

---

### 📋 PR #6: Decision Logging & Traceability (NOT YET CREATED)

**Status:** Planned  
**Estimated:** 2-3 hours effort

**What:** Log orchestrator decisions for post-run analysis.

**Expected changes:**
- New `OrchestratorDecision` dataclass
- Updated `CycleResult` to track decisions
- Decision logging in orchestrators
- Tests for decision tracking

**Benefits:** Understand *why* orchestrator chose each agent

---

## How to Use These PRs

### For Reviewers

1. **Check out each PR branch:**
   ```bash
   git fetch
   git checkout feature/phase1-error-handling
   ```

2. **Review the description:**
   - Read `PR_N_DESCRIPTION.md` for context
   - Review the code in `kodo/` and `tests/`

3. **Run tests:**
   ```bash
   pytest tests/test_error_handling.py -v
   ```

4. **Approve and merge** (or request changes)

5. **Repeat for next PR** (when ready)

### For Implementation

Follow these steps for each PR:

1. **Create feature branch** from `main`:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feature/phase-N-<description>
   ```

2. **Implement the PR** (files + tests)

3. **Test thoroughly:**
   ```bash
   pytest tests/ -m "not live" -v
   ```

4. **Push to GitHub:**
   ```bash
   git push origin feature/phase-N-<description>
   ```

5. **Create PR** on GitHub with description from `PR_N_DESCRIPTION.md`

6. **Wait for review** and approval

7. **Merge to main** once approved

8. **Start next PR** on new feature branch

---

## Merge Strategy

**Option A: Sequential (Recommended)**
1. Merge PR #1
2. Merge PR #2
3. Create PR #3 (now depends on PR #1)
4. etc.

**Option B: Parallel (Faster, may need conflict resolution)**
1. Create all PRs simultaneously
2. Merge in order
3. Resolve any conflicts as they arise

**Recommended:** Option A (cleaner, less conflict risk)

---

## Testing Each PR

### Before Merging:

```bash
# Run PR-specific tests
pytest tests/test_error_handling.py -v
pytest tests/test_config_schemas.py -v

# Run full test suite (ensure no regressions)
pytest tests/ -m "not live" -v

# Type checking (if configured)
mypy kodo/
```

### After Merging:

```bash
# Verify main branch is healthy
pytest tests/ -m "not live" -v

# Run integration tests
pytest tests/test_integration_runs.py -v
```

---

## Timeline Estimate

| PR | Phase | LOC | Tests | Effort | Timeline |
|----|-------|-----|-------|--------|----------|
| #0 | Analysis | 200 | - | 1h | Week 1 |
| #1 | Error Handling | 200 | 25+ | 2-3h | Week 1 |
| #2 | Config Schemas | 350 | 40+ | 2-3h | Week 2 |
| #3 | Session Retry | 150 | 15+ | 3-4h | Week 2-3 |
| #4 | Config Integration | 100 | 10+ | 2-3h | Week 3 |
| #5 | Context Budget | 200 | 20+ | 3-4h | Week 4 |
| #6 | Decision Logging | 150 | 15+ | 2-3h | Week 4-5 |

**Total:** ~20-25 hours over 4-5 weeks

---

## Key Principles

1. **Small PRs** — Each PR is < 500 lines of code
2. **Full tests** — Every PR has 15+ test cases
3. **Independent** — Each PR can be reviewed/merged separately
4. **Documented** — Each PR has a detailed description
5. **No breaking changes** — All PRs are backward compatible

---

## Questions?

Refer to individual PR descriptions (`PR_N_DESCRIPTION.md`) for:
- Detailed feature explanations
- Code examples
- Integration points
- Benefits and impact

---

**Generated:** 2026-02-24  
**Total PRs:** 6  
**Recommended Pace:** 1 PR/week
