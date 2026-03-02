"""
Krippendorff's Alpha computation for evaluator reliability.

Measures inter-run agreement when the same evaluator scores the same
case multiple times. Alpha >= 0.6 is the gate check for Phase 1.

Usage:
    python3 research_agent/benchmarks/compute_alpha.py results/run_XXXX/
    python3 research_agent/benchmarks/compute_alpha.py results/run_XXXX/ --verbose
"""

import json
import sys
from pathlib import Path
from itertools import combinations


def krippendorff_alpha_nominal(units: list[list]) -> float:
    """Compute Krippendorff's alpha for nominal data.

    Args:
        units: List of units, where each unit is a list of coder values.
               Missing values represented as None.
               Example: [[3, 4, 3, 3, 4], [2, 2, 3, 2, 2]] = 2 units, 5 coders

    Returns:
        Alpha value (-1 to 1). 1 = perfect agreement, 0 = chance, <0 = worse than chance.
    """
    # Flatten all observed values to get the set of categories
    all_values = []
    for unit in units:
        for v in unit:
            if v is not None:
                all_values.append(v)

    if not all_values:
        return 0.0

    # Observed disagreement (D_o)
    # For each unit, count pairwise disagreements among coders
    n_total_pairs = 0
    n_disagreements = 0

    for unit in units:
        values = [v for v in unit if v is not None]
        m = len(values)
        if m < 2:
            continue
        for i in range(m):
            for j in range(i + 1, m):
                n_total_pairs += 1
                if values[i] != values[j]:
                    n_disagreements += 1

    if n_total_pairs == 0:
        return 1.0  # No pairs to compare

    d_o = n_disagreements / n_total_pairs

    # Expected disagreement (D_e)
    # Probability that two randomly drawn values from the full pool differ
    n = len(all_values)
    if n < 2:
        return 1.0

    from collections import Counter
    counts = Counter(all_values)
    d_e = 1.0 - sum(c * (c - 1) for c in counts.values()) / (n * (n - 1))

    if d_e == 0:
        return 1.0  # All values identical

    alpha = 1.0 - (d_o / d_e)
    return alpha


def krippendorff_alpha_interval(units: list[list]) -> float:
    """Compute Krippendorff's alpha for interval/ratio data.

    Uses squared difference as the distance metric.

    Args:
        units: List of units, each a list of numeric coder values (None for missing).

    Returns:
        Alpha value.
    """
    all_values = []
    for unit in units:
        for v in unit:
            if v is not None:
                all_values.append(v)

    if not all_values:
        return 0.0

    # Observed disagreement (D_o) using squared differences
    n_total_pairs = 0
    sum_sq_diff = 0.0

    for unit in units:
        values = [v for v in unit if v is not None]
        m = len(values)
        if m < 2:
            continue
        for i in range(m):
            for j in range(i + 1, m):
                n_total_pairs += 1
                sum_sq_diff += (values[i] - values[j]) ** 2

    if n_total_pairs == 0:
        return 1.0

    d_o = sum_sq_diff / n_total_pairs

    # Expected disagreement (D_e) — avg squared diff of all value pairs in pool
    n = len(all_values)
    if n < 2:
        return 1.0

    total_sq = 0.0
    total_pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            total_sq += (all_values[i] - all_values[j]) ** 2
            total_pairs += 1

    d_e = total_sq / total_pairs

    if d_e == 0:
        return 1.0

    return 1.0 - (d_o / d_e)


def load_eval_runs(results_dir: Path) -> dict:
    """Load all evaluation runs grouped by case_id.

    Expects files named: {case_id}_eval_run{N}.json
    Falls back to: {case_id}_eval.json for single runs.

    Returns:
        Dict of case_id -> list of eval dicts
    """
    evals = {}
    for f in sorted(results_dir.glob("*_eval*.json")):
        if f.name == "summary.json":
            continue
        with open(f) as fh:
            data = json.load(fh)

        case_id = data.get("case_id", f.stem.split("_eval")[0])
        evals.setdefault(case_id, []).append(data)

    return evals


def extract_scores(eval_runs: list[dict]) -> dict:
    """Extract numeric scores from eval runs into per-metric lists.

    Returns:
        Dict of metric_name -> list of values (one per run)
    """
    metrics = {
        "single_insight": [],
        "single_novelty": [],
        "debate_insight": [],
        "debate_novelty": [],
        "debate_value": [],
    }

    for run in eval_runs:
        if "parse_error" in run or "error" in run:
            for k in metrics:
                metrics[k].append(None)
            continue

        sa = run.get("single_agent", {})
        ds = run.get("debate_system", {})

        metrics["single_insight"].append(sa.get("insight_recovery"))
        metrics["single_novelty"].append(sa.get("novelty"))
        metrics["debate_insight"].append(ds.get("insight_recovery"))
        metrics["debate_novelty"].append(ds.get("novelty"))
        metrics["debate_value"].append(run.get("debate_value"))

    return metrics


def extract_component_scores(eval_runs: list[dict]) -> dict:
    """Extract component recovery as nominal data.

    Maps RECOVERED=2, PARTIAL=1, MISSED=0.
    Returns dict of component_name -> list of values per run.
    """
    component_map = {"RECOVERED": 2, "PARTIAL": 1, "MISSED": 0}
    components = {}

    for run in eval_runs:
        if "parse_error" in run or "error" in run:
            continue

        for condition in ["single_agent", "debate_system"]:
            cr = run.get(condition, {}).get("component_recovery", {})
            for comp_name, value in cr.items():
                key = f"{condition}_{comp_name}"
                components.setdefault(key, []).append(
                    component_map.get(value, None)
                )

    return components


def compute_case_alpha(eval_runs: list[dict], verbose: bool = False) -> dict:
    """Compute alpha for all metrics of a single case across runs."""
    scores = extract_scores(eval_runs)
    components = extract_component_scores(eval_runs)

    results = {}

    # Interval alpha for numeric scores
    for metric, values in scores.items():
        clean = [v for v in values if v is not None]
        if len(clean) < 2:
            results[metric] = {"alpha": None, "n_runs": len(clean), "values": clean}
            continue

        # Each "unit" is the metric itself; each "coder" is a run
        # For single-metric alpha, we have 1 unit with N coders
        # This degenerates — we need multiple units for meaningful alpha
        # So we'll compute across cases later. Per-case, report variance.
        mean_val = sum(clean) / len(clean)
        variance = sum((v - mean_val) ** 2 for v in clean) / len(clean)
        score_range = max(clean) - min(clean)

        results[metric] = {
            "mean": round(mean_val, 2),
            "min": min(clean),
            "max": max(clean),
            "range": score_range,
            "variance": round(variance, 2),
            "n_runs": len(clean),
            "values": clean,
        }

        if verbose:
            print(f"  {metric}: mean={mean_val:.2f}, range={score_range}, "
                  f"var={variance:.2f}, values={clean}")

    # Component recovery consistency
    for comp, values in components.items():
        clean = [v for v in values if v is not None]
        if len(clean) < 2:
            continue

        from collections import Counter
        counts = Counter(clean)
        mode = counts.most_common(1)[0]
        agreement = mode[1] / len(clean)

        results[f"comp_{comp}"] = {
            "agreement": round(agreement, 2),
            "values": clean,
            "n_runs": len(clean),
        }

        if verbose:
            label_map = {2: "RECOVERED", 1: "PARTIAL", 0: "MISSED"}
            vals_str = [label_map.get(v, str(v)) for v in clean]
            print(f"  {comp}: agreement={agreement:.0%}, values={vals_str}")

    return results


def compute_cross_case_alpha(all_case_results: dict) -> dict:
    """Compute Krippendorff's alpha across cases for each metric.

    This is the proper computation: each case is a 'unit', each run is a 'coder'.
    """
    # Collect all metric names
    metric_names = set()
    for case_results in all_case_results.values():
        for key, val in case_results.items():
            if "values" in val and not key.startswith("comp_"):
                metric_names.add(key)

    alphas = {}
    for metric in sorted(metric_names):
        units = []
        for case_id, case_results in sorted(all_case_results.items()):
            if metric in case_results and "values" in case_results[metric]:
                units.append(case_results[metric]["values"])

        if len(units) < 2:
            alphas[metric] = None
            continue

        # Pad units to same length (None for missing runs)
        max_runs = max(len(u) for u in units)
        padded = [u + [None] * (max_runs - len(u)) for u in units]

        alpha = krippendorff_alpha_interval(padded)
        alphas[metric] = round(alpha, 3)

    # Component recovery (nominal)
    comp_names = set()
    for case_results in all_case_results.values():
        for key in case_results:
            if key.startswith("comp_"):
                comp_names.add(key)

    for comp in sorted(comp_names):
        units = []
        for case_id, case_results in sorted(all_case_results.items()):
            if comp in case_results and "values" in case_results[comp]:
                units.append(case_results[comp]["values"])

        if len(units) < 2:
            alphas[comp] = None
            continue

        max_runs = max(len(u) for u in units)
        padded = [u + [None] * (max_runs - len(u)) for u in units]

        alpha = krippendorff_alpha_nominal(padded)
        alphas[comp] = round(alpha, 3)

    return alphas


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python3 compute_alpha.py <results_dir> [--verbose]")
        return

    results_dir = Path(args[0])
    verbose = "--verbose" in args

    if not results_dir.exists():
        print(f"Directory not found: {results_dir}")
        return

    evals = load_eval_runs(results_dir)

    if not evals:
        print(f"No evaluation files found in {results_dir}")
        return

    print(f"{'='*60}")
    print("EVALUATOR RELIABILITY ANALYSIS (Phase 1)")
    print(f"{'='*60}")
    print(f"Results directory: {results_dir}")
    print(f"Cases found: {len(evals)}")

    all_case_results = {}
    for case_id, runs in sorted(evals.items()):
        print(f"\n--- {case_id} ({len(runs)} runs) ---")
        case_results = compute_case_alpha(runs, verbose=verbose)
        all_case_results[case_id] = case_results

    # Cross-case alpha (only meaningful with multiple cases)
    if len(all_case_results) >= 2:
        print(f"\n{'='*60}")
        print("CROSS-CASE KRIPPENDORFF'S ALPHA")
        print(f"{'='*60}")

        alphas = compute_cross_case_alpha(all_case_results)

        for metric, alpha in alphas.items():
            if alpha is not None:
                status = "PASS" if alpha >= 0.6 else "FAIL"
                print(f"  {metric:<30} alpha={alpha:>6.3f}  [{status}]")
            else:
                print(f"  {metric:<30} alpha=  N/A   [insufficient data]")

        # Overall gate check
        numeric_alphas = [a for a in alphas.values()
                          if a is not None and not any(
                              k.startswith("comp_") for k, v in alphas.items() if v == a
                          )]
        if numeric_alphas:
            min_alpha = min(numeric_alphas)
            avg_alpha = sum(numeric_alphas) / len(numeric_alphas)
            print(f"\n  Min alpha (numeric): {min_alpha:.3f}")
            print(f"  Avg alpha (numeric): {avg_alpha:.3f}")
            gate = "PASS" if min_alpha >= 0.6 else "FAIL"
            print(f"\n  GATE CHECK (alpha >= 0.6): {gate}")
    else:
        print("\nNeed 2+ cases for cross-case alpha. Per-case variance shown above.")

        # Single-case summary
        for case_id, case_results in all_case_results.items():
            print(f"\n  Per-run score ranges for {case_id}:")
            for metric, data in case_results.items():
                if "range" in data:
                    print(f"    {metric}: range={data['range']}, "
                          f"var={data['variance']}")

    # Save results
    output = {
        "cases": {
            case_id: {
                k: v for k, v in results.items()
            }
            for case_id, results in all_case_results.items()
        },
    }
    if len(all_case_results) >= 2:
        output["cross_case_alpha"] = compute_cross_case_alpha(all_case_results)

    output_path = results_dir / "alpha_analysis.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
