#!/usr/bin/env python3
"""Debate log validator — checks entries against the required schema.

Usage:
    python3 research_agent/validate_debate.py research_agent/docs/debate_log.md
    python3 research_agent/validate_debate.py research_agent/docs/debate_log.md --entry -1
    python3 research_agent/validate_debate.py research_agent/docs/debate_log.md --strict
"""

import argparse
import re
import sys


REQUIRED_SECTIONS = [
    "## Decision:",
    "**Date**:",
    "**Question**:",
    "**Question Type**:",
    "### Advocate Positions",
    "### Key Insight",
    "### Decision",
    "### Synthesis Traceability",
    "### Falsifier Assessment",
    "### Overconfidence Calibration",
    "### Confidence",
    "### Next Action",
]

ADVOCATE_NAMES = ["Empiricist", "Theorist", "Contrarian"]

PLACEHOLDER_PATTERNS = [
    r"\[N%\]",
    r"\[today\]",
    r"\[short title\]",
    r"\[debate question\]",
    r"\[type\]",
    r"\[question\]",
    r"\[1-2 sentence summary\]",
    r"\[The thing the debate revealed",
    r"\[The recommendation\]",
    r"\[Pass/Conditional/Fail",
    r"\[HIGH/MEDIUM/LOW",
    r"\[Concrete next step",
    r"\[For each recommendation element",
    r"\[justification\]",
    r"\[OVERCONFIDENCE WARNING / NORMAL / LOW VIABILITY WARNING\]",
]


def split_entries(text: str) -> list[str]:
    """Split debate log into individual entries by '## Decision:' headers."""
    parts = re.split(r"(?=^## Decision:)", text, flags=re.MULTILINE)
    return [p.strip() for p in parts if p.strip().startswith("## Decision:")]


def check_required_sections(entry: str) -> list[str]:
    """Check that all required sections are present."""
    failures = []
    for section in REQUIRED_SECTIONS:
        if section not in entry:
            failures.append(f"MISSING SECTION: '{section}' not found")
    # Check advocate names under Advocate Positions
    if "### Advocate Positions" in entry:
        for name in ADVOCATE_NAMES:
            pattern = rf"\*\*{name}\*\*"
            if not re.search(pattern, entry):
                failures.append(f"MISSING ADVOCATE: '{name}' not found under Advocate Positions")
    return failures


def check_traceability(entry: str) -> list[str]:
    """Check for traceability markers in the Decision section (strict mode)."""
    failures = []
    # Extract content between ### Decision and the next ### heading
    match = re.search(
        r"### Decision\n(.*?)(?=\n### |\Z)", entry, re.DOTALL
    )
    if not match:
        failures.append("TRACEABILITY: Could not find ### Decision section content")
        return failures

    decision_text = match.group(1)
    from_tags = re.findall(r"\[from\s+\w+\s+R\d\]", decision_text)
    supervisor_tags = re.findall(r"\[supervisor addition[^\]]*\]", decision_text)

    if len(from_tags) == 0:
        failures.append(
            "TRACEABILITY: No [from Advocate RN] tags found in Decision section"
        )
    if len(supervisor_tags) == 0:
        failures.append(
            "TRACEABILITY WARNING: No [supervisor addition] tags found "
            "(this is a warning — not all decisions need supervisor additions)"
        )
    return failures


def check_calibration(entry: str) -> list[str]:
    """Check overconfidence calibration numbers."""
    failures = []
    match = re.search(
        r"### Overconfidence Calibration\n(.*?)(?=\n### |\Z)", entry, re.DOTALL
    )
    if not match:
        failures.append("CALIBRATION: Could not find ### Overconfidence Calibration section")
        return failures

    cal_text = match.group(1)

    # Check for placeholder patterns in calibration
    if re.search(r"\[N%\]", cal_text):
        failures.append("CALIBRATION: Contains placeholder [N%] — not filled in")
        return failures

    # Extract percentages from advocate lines
    prob_pattern = r"(?:Empiricist|Theorist|Contrarian)\s+failure\s+probability:\s*(\d+)%"
    probs = re.findall(prob_pattern, cal_text)

    if len(probs) < 3:
        failures.append(
            f"CALIBRATION: Found {len(probs)}/3 failure-probability values "
            f"(expected lines for Empiricist, Theorist, Contrarian)"
        )
        return failures

    values = [int(p) for p in probs[:3]]
    total = sum(values)

    # Check if sum line exists and matches
    sum_match = re.search(r"Sum:\s*(\d+)%", cal_text)
    if sum_match:
        stated_sum = int(sum_match.group(1))
        if stated_sum != total:
            failures.append(
                f"CALIBRATION: Stated sum ({stated_sum}%) doesn't match "
                f"actual sum ({total}%) of {values[0]}+{values[1]}+{values[2]}"
            )
    else:
        failures.append("CALIBRATION: No 'Sum: N%' line found")

    # Threshold warnings (informational, still counted as failures for strict validation)
    if total < 60:
        failures.append(
            f"CALIBRATION FLAG: Sum {total}% < 60% — OVERCONFIDENCE WARNING should be noted"
        )
    elif total > 250:
        failures.append(
            f"CALIBRATION FLAG: Sum {total}% > 250% — LOW VIABILITY WARNING should be noted"
        )

    return failures


def check_advocate_diversity(entry: str) -> list[str]:
    """Check that advocate summaries are not all identical."""
    failures = []
    summaries = []
    for name in ADVOCATE_NAMES:
        pattern = rf"\*\*{name}\*\*:\s*(.+)"
        match = re.search(pattern, entry)
        if match:
            summaries.append(match.group(1).strip())

    if len(summaries) >= 2:
        unique = set(summaries)
        if len(unique) == 1:
            failures.append(
                "DIVERSITY: All advocate summaries are identical — "
                "debate may not have produced genuine disagreement"
            )
    return failures


def check_no_placeholders(entry: str) -> list[str]:
    """Check that no template placeholders remain."""
    failures = []
    for pattern in PLACEHOLDER_PATTERNS:
        matches = re.findall(pattern, entry)
        if matches:
            failures.append(
                f"PLACEHOLDER: Found unfilled template text matching '{pattern}' ({len(matches)}x)"
            )
    return failures


def validate_entry(entry: str, strict: bool = False) -> tuple[list[str], list[str]]:
    """Validate a single debate log entry.

    Returns (failures, warnings) where warnings are non-blocking.
    """
    failures = []
    warnings = []

    # 1. Required sections
    failures.extend(check_required_sections(entry))

    # 2. Traceability (strict only for failures, always check for warnings)
    trace_results = check_traceability(entry)
    for r in trace_results:
        if "WARNING" in r:
            warnings.append(r)
        elif strict:
            failures.append(r)
        else:
            warnings.append(r)

    # 3. Calibration numbers
    failures.extend(check_calibration(entry))

    # 4. Advocate diversity
    div_results = check_advocate_diversity(entry)
    for r in div_results:
        warnings.append(r)

    # 5. No placeholders
    failures.extend(check_no_placeholders(entry))

    return failures, warnings


def main():
    parser = argparse.ArgumentParser(description="Validate debate log entries")
    parser.add_argument("file", help="Path to debate_log.md")
    parser.add_argument(
        "--entry",
        type=int,
        default=None,
        help="Index of entry to validate (0-based, or -1 for last). Default: all entries.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also check traceability markers as hard failures",
    )
    args = parser.parse_args()

    with open(args.file) as f:
        text = f.read()

    entries = split_entries(text)
    if not entries:
        print("ERROR: No debate entries found in file")
        sys.exit(1)

    if args.entry is not None:
        try:
            entries = [entries[args.entry]]
        except IndexError:
            print(f"ERROR: Entry index {args.entry} out of range (found {len(entries)} entries)")
            sys.exit(1)
        entry_indices = [args.entry if args.entry >= 0 else len(split_entries(text)) + args.entry]
    else:
        entry_indices = list(range(len(entries)))

    all_passed = True

    for idx, entry in zip(entry_indices, entries):
        # Extract title
        title_match = re.match(r"## Decision:\s*(.+)", entry)
        title = title_match.group(1) if title_match else f"Entry {idx}"

        print(f"\n{'='*60}")
        print(f"Entry {idx}: {title}")
        print(f"{'='*60}")

        failures, warnings = validate_entry(entry, strict=args.strict)

        if failures:
            all_passed = False
            for f in failures:
                print(f"  FAIL: {f}")
        if warnings:
            for w in warnings:
                print(f"  WARN: {w}")
        if not failures and not warnings:
            print("  ALL CHECKS PASSED")
        elif not failures:
            print("  PASSED (with warnings)")

    print(f"\n{'='*60}")
    if all_passed:
        print("RESULT: ALL ENTRIES PASSED")
        sys.exit(0)
    else:
        print("RESULT: SOME ENTRIES FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
