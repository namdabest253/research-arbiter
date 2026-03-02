"""Tests for the debate log validator."""

import pytest

from research_agent.validate_debate import (
    check_advocate_diversity,
    check_calibration,
    check_no_placeholders,
    check_required_sections,
    check_traceability,
    split_entries,
    validate_entry,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_ENTRY = """\
## Decision: Test Approach Selection
**Date**: 2026-02-26
**Question**: Should we use approach A or approach B?
**Question Type**: Strategic

### Advocate Positions (Round 2 Final)
- **Empiricist**: Approach A is better because of metric X.
- **Theorist**: Approach A aligns with theoretical framework Y.
- **Contrarian**: Approach B has merit but A wins on evidence.

### Key Insight
The debate revealed that metric X and framework Y converge on approach A.

### Decision
- Use approach A with modification Z [from Empiricist R2]
- Apply theoretical constraint from framework Y [from Theorist R1]
- Add monitoring for the risk identified by Contrarian [supervisor addition — addresses blind spot]

### Synthesis Traceability
- Approach A selection: [from Empiricist R2] — strongest empirical support
- Framework Y constraint: [from Theorist R1] — mathematical justification
- Monitoring criteria: [supervisor addition] — neither advocate proposed this explicitly

### Falsifier Assessment
CONDITIONAL PASS. Monitor metric X weekly; if it degrades >10%, reconsider.

### Overconfidence Calibration
- Empiricist failure probability: 25% — implementation complexity may be underestimated
- Theorist failure probability: 20% — theoretical assumptions may not hold in practice
- Contrarian failure probability: 35% — alternative approach B has unexplored advantages
- Sum: 80% — NORMAL

### Confidence
MEDIUM — good convergence but limited empirical validation

### Next Action
Implement approach A with framework Y constraints and run validation suite.
"""

ENTRY_MISSING_TRACEABILITY = VALID_ENTRY.replace(
    "### Synthesis Traceability\n"
    "- Approach A selection: [from Empiricist R2] — strongest empirical support\n"
    "- Framework Y constraint: [from Theorist R1] — mathematical justification\n"
    "- Monitoring criteria: [supervisor addition] — neither advocate proposed this explicitly\n",
    "",
)

ENTRY_MISSING_CALIBRATION = VALID_ENTRY.replace(
    "### Overconfidence Calibration\n"
    "- Empiricist failure probability: 25% — implementation complexity may be underestimated\n"
    "- Theorist failure probability: 20% — theoretical assumptions may not hold in practice\n"
    "- Contrarian failure probability: 35% — alternative approach B has unexplored advantages\n"
    "- Sum: 80% — NORMAL\n",
    "",
)

ENTRY_PLACEHOLDER_CALIBRATION = VALID_ENTRY.replace(
    "- Empiricist failure probability: 25% — implementation complexity may be underestimated\n"
    "- Theorist failure probability: 20% — theoretical assumptions may not hold in practice\n"
    "- Contrarian failure probability: 35% — alternative approach B has unexplored advantages\n"
    "- Sum: 80% — NORMAL",
    "- Empiricist failure probability: [N%] — [justification]\n"
    "- Theorist failure probability: [N%] — [justification]\n"
    "- Contrarian failure probability: [N%] — [justification]\n"
    "- Sum: [N%] — [OVERCONFIDENCE WARNING / NORMAL / LOW VIABILITY WARNING]",
)

ENTRY_WRONG_SUM = VALID_ENTRY.replace("Sum: 80%", "Sum: 50%")

ENTRY_IDENTICAL_ADVOCATES = VALID_ENTRY.replace(
    "- **Empiricist**: Approach A is better because of metric X.\n"
    "- **Theorist**: Approach A aligns with theoretical framework Y.\n"
    "- **Contrarian**: Approach B has merit but A wins on evidence.",
    "- **Empiricist**: Use approach A.\n"
    "- **Theorist**: Use approach A.\n"
    "- **Contrarian**: Use approach A.",
)

ENTRY_NO_TRACEABILITY_TAGS = VALID_ENTRY.replace(
    "### Decision\n"
    "- Use approach A with modification Z [from Empiricist R2]\n"
    "- Apply theoretical constraint from framework Y [from Theorist R1]\n"
    "- Add monitoring for the risk identified by Contrarian [supervisor addition — addresses blind spot]",
    "### Decision\n"
    "- Use approach A with modification Z\n"
    "- Apply theoretical constraint from framework Y\n"
    "- Add monitoring for the risk identified by Contrarian",
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSplitEntries:
    def test_splits_multiple_entries(self):
        text = "# Header\nSome preamble\n\n" + VALID_ENTRY + "\n---\n\n" + VALID_ENTRY
        entries = split_entries(text)
        assert len(entries) == 2

    def test_no_entries(self):
        assert split_entries("# Just a header\nNo entries here") == []


class TestValidEntry:
    def test_all_checks_pass(self):
        failures, warnings = validate_entry(VALID_ENTRY, strict=True)
        # Filter out the supervisor addition warning (it's expected)
        real_failures = [f for f in failures if "WARNING" not in f]
        assert real_failures == [], f"Unexpected failures: {real_failures}"

    def test_required_sections_pass(self):
        assert check_required_sections(VALID_ENTRY) == []


class TestMissingSections:
    def test_missing_traceability_section(self):
        failures, _ = validate_entry(ENTRY_MISSING_TRACEABILITY)
        section_failures = [f for f in failures if "### Synthesis Traceability" in f]
        assert len(section_failures) > 0

    def test_missing_calibration_section(self):
        failures, _ = validate_entry(ENTRY_MISSING_CALIBRATION)
        section_failures = [f for f in failures if "Overconfidence Calibration" in f]
        assert len(section_failures) > 0


class TestCalibration:
    def test_placeholder_calibration_fails(self):
        failures, _ = validate_entry(ENTRY_PLACEHOLDER_CALIBRATION)
        cal_failures = [f for f in failures if "CALIBRATION" in f or "PLACEHOLDER" in f]
        assert len(cal_failures) > 0

    def test_wrong_sum_fails(self):
        failures, _ = validate_entry(ENTRY_WRONG_SUM)
        sum_failures = [f for f in failures if "sum" in f.lower() or "Sum" in f]
        assert len(sum_failures) > 0, f"Expected sum mismatch failure, got: {failures}"


class TestAdvocateDiversity:
    def test_identical_advocates_warns(self):
        _, warnings = validate_entry(ENTRY_IDENTICAL_ADVOCATES)
        div_warnings = [w for w in warnings if "DIVERSITY" in w]
        assert len(div_warnings) > 0


class TestTraceability:
    def test_with_tags_strict_passes(self):
        failures, _ = validate_entry(VALID_ENTRY, strict=True)
        trace_failures = [f for f in failures if "TRACEABILITY" in f and "WARNING" not in f]
        assert trace_failures == []

    def test_without_tags_strict_fails(self):
        failures, _ = validate_entry(ENTRY_NO_TRACEABILITY_TAGS, strict=True)
        trace_failures = [f for f in failures if "TRACEABILITY" in f and "WARNING" not in f]
        assert len(trace_failures) > 0

    def test_without_tags_non_strict_warns(self):
        failures, warnings = validate_entry(ENTRY_NO_TRACEABILITY_TAGS, strict=False)
        trace_failures = [f for f in failures if "TRACEABILITY" in f]
        trace_warnings = [w for w in warnings if "TRACEABILITY" in w]
        assert trace_failures == [], "Non-strict should not fail on traceability"
        assert len(trace_warnings) > 0, "Non-strict should warn on missing traceability"


class TestPlaceholders:
    def test_detects_placeholder_patterns(self):
        failures = check_no_placeholders(
            "## Decision: [short title]\n**Date**: [today]\nSome [N%] value"
        )
        assert len(failures) >= 2
