"""
build_cases.py — Novelty Benchmark Case Pipeline

This script documents the workflow for building new benchmark cases.
The actual pipeline is driven from Claude Code's main conversation using
Task agents (not this script directly), because paper reading and LLM
probing require agent-mediated tool calls.

## Pipeline Overview

1. Paper Discovery
   - Search arXiv and Semantic Scholar for outstanding/best papers from
     NeurIPS, ICML, ICLR in the target year window
   - Filter for clear problem→insight structure (not surveys, not incremental)
   - Target 12-15 candidates to produce 8-10 good cases

   Tools:
     python3 research_agent/tools.py search-ss "query" --year 2025-2026 --max-results 10
     python3 research_agent/tools.py search "query" --max-results 10

2. Case Extraction
   - For each candidate paper, read first 5-6 pages
   - Extract: problem_statement, known_ingredients (3-7), key_insight,
     insight_components (3-5), difficulty, difficulty_rationale, domain

   Tools:
     python3 research_agent/tools.py read <arxiv_id> --pages 1-6

3. Contamination Probing
   - For each candidate, launch a Haiku agent with the following probe:
     Q1: "Do you know a paper titled [title]? What is its main contribution?"
     Q2: "Given [problem_statement], what would you propose?" (no ingredients)
   - Classify tier based on response:
     Tier 1: Cannot identify paper OR approximate its result
     Tier 2: Knows ingredients/direction but not specific combination
     Tier 3: Can identify paper or closely approximate result

4. Case File Generation
   - Write case JSON files to research_agent/benchmarks/cases/
   - Schema: see cases/case_006.json through case_012.json for reference
   - Required fields: id, paper, problem_statement, known_ingredients,
     key_insight, insight_components, difficulty, difficulty_rationale,
     domain, contamination_risk, contamination_tier, contamination_probe_results
   - Update research_agent/docs/novelty_benchmark_results.md with inventory

## JSON Schema

{
  "id": "case_NNN",
  "paper": {
    "title": "...",
    "arxiv_id": "...",
    "year": 2025,
    "venue": "...",
    "authors": ["..."]
  },
  "problem_statement": "...",
  "known_ingredients": ["...", "...", "..."],  // 3-8 items
  "key_insight": "...",
  "insight_components": ["...", "...", "..."],  // 3-5 items
  "difficulty": "easy|medium|hard",
  "difficulty_rationale": "...",
  "domain": "...",
  "contamination_risk": "low|medium|high",
  "contamination_tier": 1,                     // 1=clean, 2=partial, 3=contaminated
  "contamination_probe_results": {
    "q1_title_recognition": "...",
    "q2_proposed_approach_summary": "...",
    "tier_assigned_by_probe": 1,
    "tier_assigned_by_human": 1,
    "human_tier_rationale": "...",
    "probe_model": "claude-haiku-4-5"
  }
}

## Validation

Run the validator to check all case files:
  python3 research_agent/benchmarks/build_cases.py --validate

## Cases Built

Phase 1 (2026-02-27): case_001 through case_005
  - 4 high-contamination Tier 3 cases (CFG, FSQ, DDPM, LoRA)
  - 1 internal project case (VQ-VAE v16b)

Phase 2 (2026-03-01): case_006 through case_012
  - 3 Tier 1 (clean): case_007, case_008, case_012
  - 4 Tier 2 (partial): case_006, case_009, case_010, case_011
  - Sources: NeurIPS 2025 best papers, ICML 2025 outstanding papers, ICLR 2026
"""

import json
import sys
import pathlib

CASES_DIR = pathlib.Path(__file__).parent / "cases"

REQUIRED_FIELDS = [
    "id", "paper", "problem_statement", "known_ingredients",
    "key_insight", "insight_components", "difficulty",
    "difficulty_rationale", "domain",
]
PAPER_FIELDS = ["title", "arxiv_id", "year", "venue", "authors"]


def validate_case(path: pathlib.Path) -> list[str]:
    """Return list of validation errors for a case file."""
    errors = []
    try:
        case = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return [f"JSON parse error: {e}"]

    for field in REQUIRED_FIELDS:
        if field not in case:
            errors.append(f"Missing required field: {field}")

    paper = case.get("paper", {})
    for field in PAPER_FIELDS:
        if field not in paper:
            errors.append(f"Missing paper.{field}")

    ingredients = case.get("known_ingredients", [])
    if not (3 <= len(ingredients) <= 8):
        errors.append(f"known_ingredients must have 3-8 items, got {len(ingredients)}")

    components = case.get("insight_components", [])
    if not (3 <= len(components) <= 5):
        errors.append(f"insight_components must have 3-5 items, got {len(components)}")

    difficulty = case.get("difficulty")
    if difficulty not in ("easy", "medium", "hard"):
        errors.append(f"difficulty must be easy/medium/hard, got {difficulty!r}")

    tier = case.get("contamination_tier")
    if tier is not None and tier not in (1, 2, 3):
        errors.append(f"contamination_tier must be 1/2/3, got {tier!r}")

    return errors


def main():
    if "--validate" not in sys.argv:
        print(__doc__)
        return

    case_files = sorted(CASES_DIR.glob("case_*.json"))
    if not case_files:
        print("No case files found in", CASES_DIR)
        sys.exit(1)

    all_ok = True
    for path in case_files:
        errors = validate_case(path)
        if errors:
            print(f"FAIL {path.name}:")
            for err in errors:
                print(f"  - {err}")
            all_ok = False
        else:
            print(f"  OK {path.name}")

    if all_ok:
        print(f"\nAll {len(case_files)} case files valid.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
