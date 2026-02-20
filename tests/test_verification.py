"""Tests for enhanced verification checklist system.

Covers: check categories, verification prompts, report parsing,
issue detection, severity classification, metrics tracking.
"""

from __future__ import annotations

import pytest

from kodo.verification import (
    ARCHITECT_CHECKLIST,
    CheckCategory,
    Severity,
    VerificationCheck,
    VerificationIssue,
    VerificationMetrics,
    VerificationReport,
    build_verification_prompt,
    parse_verification_report,
)


# ── VerificationCheck ────────────────────────────────────────────────────


class TestVerificationCheck:
    def test_to_checklist_item(self) -> None:
        check = VerificationCheck(
            CheckCategory.SYNTAX,
            "Code syntax valid",
            "Check for syntax errors.",
        )
        item = check.to_checklist_item()
        assert "SYNTAX" in item
        assert "Code syntax valid" in item

    def test_all_categories_in_checklist(self) -> None:
        categories = {c.category for c in ARCHITECT_CHECKLIST}
        assert CheckCategory.SYNTAX in categories
        assert CheckCategory.TESTS in categories
        assert CheckCategory.SECURITY in categories
        assert CheckCategory.PERFORMANCE in categories
        assert CheckCategory.ARCHITECTURE in categories
        assert CheckCategory.CORRECTNESS in categories

    def test_checklist_has_seven_items(self) -> None:
        assert len(ARCHITECT_CHECKLIST) == 7


# ── VerificationIssue ────────────────────────────────────────────────────


class TestVerificationIssue:
    def test_location_with_file_and_line(self) -> None:
        issue = VerificationIssue(
            CheckCategory.SYNTAX,
            Severity.BLOCKER,
            "Missing import",
            file_path="src/main.py",
            line_number=42,
        )
        assert issue.location == "src/main.py:42"

    def test_location_file_only(self) -> None:
        issue = VerificationIssue(
            CheckCategory.SYNTAX,
            Severity.MAJOR,
            "Bad naming",
            file_path="src/utils.py",
        )
        assert issue.location == "src/utils.py"

    def test_location_none(self) -> None:
        issue = VerificationIssue(
            CheckCategory.TESTS,
            Severity.MINOR,
            "Flaky test",
        )
        assert issue.location == "(no location)"


# ── VerificationReport ───────────────────────────────────────────────────


class TestVerificationReport:
    def test_empty_report_is_clean(self) -> None:
        report = VerificationReport()
        assert report.is_clean
        assert report.total_issues == 0
        assert report.blocker_count == 0

    def test_report_with_blockers(self) -> None:
        report = VerificationReport(
            issues=[
                VerificationIssue(CheckCategory.SECURITY, Severity.BLOCKER, "Hardcoded key"),
                VerificationIssue(CheckCategory.SYNTAX, Severity.MINOR, "Style issue"),
            ]
        )
        assert not report.is_clean
        assert report.blocker_count == 1
        assert report.minor_count == 1
        assert report.total_issues == 2

    def test_report_with_only_minor(self) -> None:
        report = VerificationReport(
            issues=[
                VerificationIssue(CheckCategory.WARNINGS, Severity.MINOR, "Unused import"),
            ]
        )
        assert report.is_clean  # minor issues don't block

    def test_issues_by_category(self) -> None:
        report = VerificationReport(
            issues=[
                VerificationIssue(CheckCategory.SECURITY, Severity.BLOCKER, "A"),
                VerificationIssue(CheckCategory.SECURITY, Severity.MAJOR, "B"),
                VerificationIssue(CheckCategory.TESTS, Severity.MAJOR, "C"),
            ]
        )
        by_cat = report.issues_by_category
        assert len(by_cat[CheckCategory.SECURITY]) == 2
        assert len(by_cat[CheckCategory.TESTS]) == 1

    def test_summary_clean(self) -> None:
        report = VerificationReport()
        assert "ALL CHECKS PASS" in report.summary()

    def test_summary_with_issues(self) -> None:
        report = VerificationReport(
            issues=[
                VerificationIssue(CheckCategory.SYNTAX, Severity.BLOCKER, "Error"),
                VerificationIssue(CheckCategory.TESTS, Severity.MAJOR, "Failure"),
                VerificationIssue(CheckCategory.WARNINGS, Severity.MINOR, "Warning"),
            ]
        )
        summary = report.summary()
        assert "1 blocker" in summary
        assert "1 major" in summary
        assert "1 minor" in summary


# ── build_verification_prompt ────────────────────────────────────────────


class TestBuildVerificationPrompt:
    def test_contains_goal_and_summary(self) -> None:
        prompt = build_verification_prompt(
            goal="Add login feature",
            summary="Implemented OAuth2 login",
        )
        assert "Add login feature" in prompt
        assert "Implemented OAuth2 login" in prompt

    def test_contains_checklist_items(self) -> None:
        prompt = build_verification_prompt("goal", "summary")
        assert "SYNTAX" in prompt
        assert "TESTS" in prompt
        assert "SECURITY" in prompt
        assert "PERFORMANCE" in prompt

    def test_contains_reporting_format(self) -> None:
        prompt = build_verification_prompt("goal", "summary")
        assert "Category" in prompt
        assert "Severity" in prompt
        assert "ALL CHECKS PASS" in prompt

    def test_custom_checklist(self) -> None:
        custom = [
            VerificationCheck(
                CheckCategory.TESTS,
                "Custom check",
                "Run custom verification.",
            )
        ]
        prompt = build_verification_prompt("goal", "summary", checklist=custom)
        assert "Custom check" in prompt
        # Should NOT contain default checks
        assert "hardcoded secrets" not in prompt.lower()


# ── parse_verification_report ────────────────────────────────────────────


class TestParseVerificationReport:
    def test_all_pass(self) -> None:
        report = parse_verification_report("Everything looks good. ALL CHECKS PASS")
        assert report.is_clean
        assert report.total_issues == 0

    def test_minor_issues_fixed(self) -> None:
        report = parse_verification_report(
            "Fixed some typos. MINOR ISSUES FIXED"
        )
        assert report.is_clean
        assert report.total_issues == 0

    def test_parse_structured_issue(self) -> None:
        text = """
        **SECURITY**: **BLOCKER** - `src/auth.py:42` - Hardcoded API key found
        """
        report = parse_verification_report(text)
        assert report.total_issues >= 1
        security_issues = [
            i for i in report.issues if i.category == CheckCategory.SECURITY
        ]
        assert len(security_issues) >= 1

    def test_parse_simple_blocker(self) -> None:
        text = "BLOCKER: Tests are failing with 3 errors"
        report = parse_verification_report(text)
        assert report.blocker_count >= 1

    def test_parse_simple_major(self) -> None:
        text = "MAJOR: Missing error handling in the API endpoint"
        report = parse_verification_report(text)
        assert report.major_count >= 1

    def test_parse_simple_minor(self) -> None:
        text = "MINOR: Unused import in utils.py"
        report = parse_verification_report(text)
        assert report.minor_count >= 1

    def test_parse_fail_pattern(self) -> None:
        text = "FAIL: Integration test timed out"
        report = parse_verification_report(text)
        assert report.total_issues >= 1

    def test_parse_multiple_issues(self) -> None:
        text = """
        BLOCKER: SQL injection vulnerability in user input handler
        MAJOR: No input validation on email field
        MINOR: Variable naming inconsistent
        """
        report = parse_verification_report(text)
        assert report.total_issues >= 3
        assert report.blocker_count >= 1
        assert report.major_count >= 1
        assert report.minor_count >= 1

    def test_parse_passed_checks(self) -> None:
        text = "[x] **SYNTAX** - all good\n[x] **TESTS** - passing"
        report = parse_verification_report(text)
        assert "SYNTAX" in report.checks_passed
        assert "TESTS" in report.checks_passed

    def test_empty_report(self) -> None:
        report = parse_verification_report("")
        assert report.total_issues == 0

    def test_raw_text_preserved(self) -> None:
        text = "Some verification output"
        report = parse_verification_report(text)
        assert report.raw_text == text


# ── VerificationMetrics ──────────────────────────────────────────────────


class TestVerificationMetrics:
    def test_empty_metrics(self) -> None:
        m = VerificationMetrics()
        assert m.total_verifications == 0
        assert m.detection_rate == 0.0
        assert m.bug_escape_rate == 0.0

    def test_record_clean_verification(self) -> None:
        m = VerificationMetrics()
        report = VerificationReport()
        m.record_verification(report)
        assert m.total_verifications == 1
        assert m.total_issues_found == 0

    def test_record_verification_with_issues(self) -> None:
        m = VerificationMetrics()
        report = VerificationReport(
            issues=[
                VerificationIssue(CheckCategory.SECURITY, Severity.BLOCKER, "Key exposed"),
                VerificationIssue(CheckCategory.TESTS, Severity.MAJOR, "Test fails"),
            ]
        )
        m.record_verification(report)
        assert m.total_issues_found == 2
        assert m.blockers_caught == 1
        assert m.security_issues_caught == 1

    def test_detection_rate(self) -> None:
        m = VerificationMetrics()
        # 10 verifications, no false passes
        for _ in range(10):
            m.record_verification(
                VerificationReport(
                    issues=[
                        VerificationIssue(
                            CheckCategory.CORRECTNESS, Severity.MAJOR, "Bug"
                        )
                    ]
                )
            )
        assert m.detection_rate == 1.0

    def test_bug_escape_rate(self) -> None:
        m = VerificationMetrics()
        # Found 9 bugs in verification, 1 escaped
        for _ in range(9):
            m.record_verification(
                VerificationReport(
                    issues=[
                        VerificationIssue(
                            CheckCategory.CORRECTNESS, Severity.MAJOR, "Found bug"
                        )
                    ]
                )
            )
        m.record_escaped_bug()
        # 1 escaped out of 10 total
        assert m.bug_escape_rate == pytest.approx(0.1)

    def test_zero_escape_rate_target(self) -> None:
        """Verify we can achieve <5% escape rate (the target)."""
        m = VerificationMetrics()
        # 100 verifications, each finding 1 issue
        for _ in range(100):
            m.record_verification(
                VerificationReport(
                    issues=[
                        VerificationIssue(
                            CheckCategory.CORRECTNESS, Severity.MAJOR, "Bug"
                        )
                    ]
                )
            )
        # Only 4 escapes out of 104 total = 3.8% < 5%
        for _ in range(4):
            m.record_escaped_bug()
        assert m.bug_escape_rate < 0.05

    def test_multiple_verifications(self) -> None:
        m = VerificationMetrics()
        # Mix of clean and issue-finding verifications
        m.record_verification(VerificationReport())  # clean
        m.record_verification(
            VerificationReport(
                issues=[
                    VerificationIssue(CheckCategory.SYNTAX, Severity.BLOCKER, "Error"),
                    VerificationIssue(CheckCategory.SECURITY, Severity.BLOCKER, "Key"),
                ]
            )
        )
        m.record_verification(VerificationReport())  # clean

        assert m.total_verifications == 3
        assert m.total_issues_found == 2
        assert m.blockers_caught == 2
        assert m.security_issues_caught == 1
