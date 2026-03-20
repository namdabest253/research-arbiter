# Project Decision Benchmark (PDB) — Results

**Date**: 2026-03-13
**Status**: All 5/5 cases complete.

## Aggregate Results (5 Cases)

| Criterion | Single | Debate | Lift | Interpretation |
|-----------|--------|--------|------|----------------|
| **Context Utilization** | 0.600 | 0.834 | **+0.234** | Debate references more prior results |
| **Confound Detection** | 0.334 | 0.532 | **+0.198** | Debate catches more hidden problems |
| History Anti-Repetition | 1.000 | 1.000 | 0.000 | Both avoid known failures (ceiling) |
| **Experiment Sequencing** | 0.900 | 1.000 | **+0.100** | Debate consistently adds kill criteria |
| Actionability | 1.000 | 0.900 | -0.100 | Single gives slightly more concrete details |
| Scope Awareness | 1.000 | 1.000 | 0.000 | Both see broader trajectory (ceiling) |
| **COMPOSITE** | **0.806** | **0.878** | **+0.072** | Debate wins overall |

## Key Findings

### 1. Debate's Primary Value: Context Utilization (+0.234) and Confound Detection (+0.198)

The multi-advocate structure — especially the Contrarian — surfaces prior results and hidden problems that a single agent misses. This held in 3/5 cases (pdb_001, pdb_002, pdb_005). In 1 case (pdb_004), the pattern reversed: single agent caught more confounds.

**Where debate won on confound detection:**
- **pdb_001**: Contrarian caught the VQ-VAE diagnostic gap (S=0.0, D=1.0 — largest single swing)
- **pdb_002**: Debate flagged model-size-to-dataset mismatch (S=0.0, D=0.33)
- **pdb_005**: Debate caught meta-improvement opportunity cost (S=0.67, D=0.67 — tied, but different confounds caught)

**Where single agent won on confound detection:**
- **pdb_004**: Single agent identified noisy tag labels AND oversized model; debate only caught oversized model (S=0.67, D=0.33)

### 2. Experiment Sequencing: Debate's Protocol Advantage (+0.100)

Debate scored a perfect 2/2 (cheapest-first + kill criteria) on all 5 cases. Single agent scored 2/2 on 4 cases but dropped to 1/2 on pdb_004 (sequenced steps but truncated before kill criteria). The forced 7-step protocol consistently produces better-structured experimental plans.

### 3. Single Agent Wins on Actionability (-0.100)

Single agent provides more concrete implementation details — specific hyperparameters, script names, dollar costs, batch sizes. Debate produces better-structured reasoning but slightly less granular execution specs. This appeared in pdb_001 (S=2, D=1) where single agent gave specific architectural changes while debate stayed at a higher level.

### 4. Three Criteria Hit Ceiling (Both = 1.0)

History Anti-Repetition, Scope Awareness, and (mostly) Actionability all hit perfect scores for both conditions. The benchmark prompt is effective at eliciting these behaviors from both — **the differentiating signal is in Context Utilization, Confound Detection, and Experiment Sequencing.**

### 5. pdb_003 Was a Complete Tie

The retest-before-pivot case showed identical scores across all 6 criteria. Both caught the same confound (criteria validation) and missed the same two (noisy labels, Colab memory). The evaluator noted the debate had qualitatively richer sequencing and a novel analytical insight, but these didn't move rubric scores. This suggests the rubric may under-weight qualitative reasoning depth.

### 6. Hardest Confounds Are "Absent Methodology" Problems

The confounds most frequently missed by both systems:
- "Evaluation criteria never validated against real positives" (missed by both on pdb_002, caught by both on pdb_003)
- "Noisy tag labels" (missed by both on pdb_003, caught by single on pdb_004)
- "Colab memory feasibility" (missed by both on pdb_003)
- "Wrong checkpoint selection" (missed by both on pdb_004)

These require reasoning about what's *absent* from the methodology — a genuinely hard reasoning task that neither single agent nor debate reliably handles.

## Per-Case Breakdown

### pdb_001 — v7 Approach (Medium) — **Debate wins**

| Criterion | Single | Debate | Winner |
|-----------|--------|--------|--------|
| Context Utilization | 0.50 | 1.00 | **Debate** |
| Confound Detection | 0.00 | 1.00 | **Debate** |
| History Anti-Repetition | 1.00 | 1.00 | Tie |
| Experiment Sequencing | 2 | 2 | Tie |
| Actionability | 2 | 1 | **Single** |
| Scope Awareness | YES | YES | Tie |

Debate's Contrarian reframed from "what model next?" to "is the test bench working?" — caught the VQ-VAE diagnostic gap. Single agent gave more concrete implementation details.

### pdb_002 — Scope Reduction (Hard) — **Debate slight edge**

| Criterion | Single | Debate | Winner |
|-----------|--------|--------|--------|
| Context Utilization | 0.50 | 0.50 | Tie |
| Confound Detection | 0.00 | 0.33 | **Debate** |
| History Anti-Repetition | 1.00 | 1.00 | Tie |
| Experiment Sequencing | 2 | 2 | Tie |
| Actionability | 2 | 2 | Tie |
| Scope Awareness | YES | YES | Tie |

Hardest case — 3 confounds, neither caught broken criteria or clustering limitation. Debate flagged model-size mismatch and surfaced a novel insight about text conditioning quality.

### pdb_003 — Retest Before Pivot (Hard) — **Tie**

| Criterion | Single | Debate | Winner |
|-----------|--------|--------|--------|
| Context Utilization | 1.00 | 1.00 | Tie |
| Confound Detection | 0.33 | 0.33 | Tie |
| History Anti-Repetition | 1.00 | 1.00 | Tie |
| Experiment Sequencing | 2 | 2 | Tie |
| Actionability | 2 | 2 | Tie |
| Scope Awareness | YES | YES | Tie |

Complete tie. Both caught criteria validation confound, both missed noisy labels and Colab memory. Debate had qualitatively richer sequencing but same rubric score.

### pdb_004 — Final Clean Test (Hard) — **Mixed**

| Criterion | Single | Debate | Winner |
|-----------|--------|--------|--------|
| Context Utilization | 1.00 | 1.00 | Tie |
| Confound Detection | 0.67 | 0.33 | **Single** |
| History Anti-Repetition | 1.00 | 1.00 | Tie |
| Experiment Sequencing | 1 | 2 | **Debate** |
| Actionability | 2 | 2 | Tie |
| Scope Awareness | YES | YES | Tie |

**Only case where single agent beat debate on confound detection.** Single agent explicitly identified noisy tag labels AND oversized model; debate only caught model size. But debate won on sequencing with a rigorous 4-step diagnostic cascade with pass/kill criteria.

### pdb_005 — Meta-Debate Self-Improvement (Medium) — **Debate wins**

| Criterion | Single | Debate | Winner |
|-----------|--------|--------|--------|
| Context Utilization | 0.00 | 0.67 | **Debate** |
| Confound Detection | 0.67 | 0.67 | Tie |
| History Anti-Repetition | 1.00 | 1.00 | Tie |
| Experiment Sequencing | 2 | 2 | Tie |
| Actionability | 2 | 2 | Tie |
| Scope Awareness | YES | YES | Tie |

Biggest context utilization gap — single agent referenced 0/3 prior results while debate referenced 2/3 (scaffold sensitivity, inconclusive diagnostic pattern). Confound detection tied but with different catches.

## Comparison with NRB (Novelty Recovery Benchmark)

| Dimension | NRB Finding | PDB Finding | Consistent? |
|-----------|------------|------------|-------------|
| Insight recovery | Debate = Single (3-4/5) | N/A (different rubric) | — |
| Experimental design | Debate > Single | Debate > Single on sequencing (+0.10) | Yes |
| Contrarian value | Double-edged | Positive in 3/5, neutral in 1/5, negative in 1/5 | Yes |
| Actionability | Not measured | Single > Debate (-0.10) | New finding |
| Context utilization | Not measured | Debate > Single (+0.23) | New finding |
| Confound detection | Not measured | Debate > Single (+0.20) | New finding |

The PDB confirms the NRB's key finding: **debate's value is in experimental design, not raw capability**. The decomposed rubric pinpoints this to context utilization and confound detection — the tunnel-vision-prevention dimensions.

## Conclusions

1. **Debate adds ~7% composite lift** over single agent on project decisions (0.878 vs 0.806)
2. **The lift comes from two specific criteria**: context utilization (+0.23) and confound detection (+0.20)
3. **The tradeoff is actionability**: single agent gives more concrete implementation details (-0.10)
4. **Debate is not uniformly better**: pdb_004 showed single agent catching more confounds. The Contrarian's value depends on the specific confounds at play
5. **Both systems are weak at detecting "absent methodology" confounds** — things that should have been done but weren't
6. **The forced protocol helps**: experiment sequencing is the one structural criterion where debate consistently outperforms

## Files

```
research_agent/benchmarks/
├── run_project_benchmark.py
├── PROJECT_BENCHMARK_IMPLEMENTATION.md   (this file)
├── project_cases/
│   ├── pdb_001.json through pdb_005.json
└── results/
    ├── pdb_run_2026-03-05_0222/          (pdb_001)
    ├── pdb_run_2026-03-11_2126/          (pdb_005)
    ├── pdb_run_2026-03-11_2218/          (pdb_002)
    ├── pdb_run_2026-03-12_1105/          (pdb_003)
    └── pdb_run_2026-03-13_2147/          (pdb_004)

research_agent/docs/
├── project_decision_benchmark.md         (design doc)
└── research_index.md                     (updated with PDB entry)
```
