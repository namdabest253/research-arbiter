# Research Agent — Multi-Agent Debate System for Claude Code

A multi-agent research system built entirely on [Claude Code](https://docs.anthropic.com/en/docs/claude-code) native agents. No Python orchestration — agents are markdown files that Claude Code launches via its `Task` tool.

**What it does:** Searches arXiv and Semantic Scholar for papers, reads and analyzes them, maintains a structured knowledge base, and orchestrates structured debates between specialist agents to make research decisions.

## How It Works

```
You (in Claude Code): "Find papers on discrete diffusion for 3D generation"
  │
  ▼
Claude Code spawns ──→ research-paper-finder agent (Sonnet)
                          │
                          ├── python3 research_agent/tools.py search "..."
                          ├── python3 research_agent/tools.py read "2303.12345"
                          ├── python3 research_agent/tools.py citations "..."
                          ├── WebSearch / WebFetch (non-arXiv sources)
                          │
                          ▼
                       Returns findings + saves to knowledge base
```

```
You: "Debate whether we should use discrete diffusion vs continuous latent diffusion"
  │
  ▼
Claude Code spawns ──→ research-supervisor agent (Opus)
                          │
                          ├── Round 1: spawns 3 advocates IN PARALLEL
                          │     ├── Empiricist (data-driven)
                          │     ├── Theorist (first-principles)
                          │     └── Contrarian (challenges assumptions)
                          │
                          ├── Round 2: advocates cross-examine each other
                          │
                          ├── Synthesis: supervisor identifies consensus
                          │
                          └── Falsification: stress-tests the winning approach
                                └── GO / CONDITIONAL / NO-GO verdict
```

## Agent Architecture

All agents live in [`.claude/agents/`](.claude/agents/). Claude Code reads these markdown files and uses them as system prompts when spawning sub-agents.

### Core Agents

| Agent | Model | File | Role |
|-------|-------|------|------|
| **research-paper-finder** | Sonnet | [`research-paper-finder.md`](.claude/agents/research-paper-finder.md) | Searches, reads, and analyzes papers. Generates debate briefs. |
| **research-supervisor** | Opus | [`research-supervisor.md`](.claude/agents/research-supervisor.md) | Orchestrates 2-round debates with synthesis + falsification. |

### Debate Advocate Sub-Agents (spawned by supervisor)

| Agent | Model | File | Epistemology |
|-------|-------|------|-------------|
| **research-advocate-empiricist** | Sonnet | [`research-advocate-empiricist.md`](.claude/agents/research-advocate-empiricist.md) | Only accepts measured results, ablations, convergence data. Every claim must cite a metric. |
| **research-advocate-theorist** | Sonnet | [`research-advocate-theorist.md`](.claude/agents/research-advocate-theorist.md) | Only accepts math, loss landscape analysis, information-theoretic bounds. Rejects "it worked" without mechanism. |
| **research-advocate-contrarian** | Sonnet | [`research-advocate-contrarian.md`](.claude/agents/research-advocate-contrarian.md) | Surfaces blind spots and unconsidered alternatives. Must commit to a specific alternative, not just critique. |

### Post-Debate Agents

| Agent | Model | File | Role |
|-------|-------|------|------|
| **research-falsifier** | Sonnet | [`research-falsifier.md`](.claude/agents/research-falsifier.md) | Stress-tests winning proposal. Designs kill criteria. Issues GO/CONDITIONAL/NO-GO. |

### Meta-Research Agents (optional — debates about the debate system itself)

| Agent | File |
|-------|------|
| **meta-research-supervisor** | [`meta-research-supervisor.md`](.claude/agents/meta-research-supervisor.md) |
| **meta-advocate-empiricist** | [`meta-advocate-empiricist.md`](.claude/agents/meta-advocate-empiricist.md) |
| **meta-advocate-theorist** | [`meta-advocate-theorist.md`](.claude/agents/meta-advocate-theorist.md) |
| **meta-advocate-contrarian** | [`meta-advocate-contrarian.md`](.claude/agents/meta-advocate-contrarian.md) |
| **meta-research-falsifier** | [`meta-research-falsifier.md`](.claude/agents/meta-research-falsifier.md) |

## Knowledge Pipeline

The paper-finder generates **debate briefs** — condensed, advocate-targeted summaries that solve the training-data-cutoff problem. When a debate happens, the supervisor injects relevant briefs so advocates can reason about research they wouldn't otherwise know about.

```
research-paper-finder
  ├── docs/[topic]_papers.md              (full detail)
  ├── docs/debate_briefs/[topic]_brief.md (condensed, <200 lines)
  │     ├── "For the Empiricist" section  → metrics, benchmarks, ablations
  │     ├── "For the Theorist" section    → math, loss landscapes, bounds
  │     └── "For the Contrarian" section  → limitations, failure modes
  └── docs/debate_briefs/brief_index.md   (topic → brief mapping)

research-supervisor (during debate)
  ├── reads brief_index.md → matches topic
  └── injects matching brief sections into each advocate's prompt
```

## Setup

1. Install [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
2. Clone this repo
3. Install Python deps:
   ```bash
   pip install -r research_agent/requirements.txt
   ```
4. Run Claude Code in the repo root — the agents are automatically available

## CLI Tools

The agents call `tools.py` via Bash. You can also use them standalone:

```bash
# Search arXiv
python3 research_agent/tools.py search "VQ-VAE 3D generation" --max-results 5

# Search Semantic Scholar
python3 research_agent/tools.py search-ss "latent diffusion 3D" --max-results 10 --year "2023-2024"

# Read a paper (downloads PDF, extracts text, caches)
python3 research_agent/tools.py read "2303.12345"
python3 research_agent/tools.py read "2303.12345" --pages "4-8"

# Citation graph traversal
python3 research_agent/tools.py citations "2107.03006" --direction both --max-results 20

# Knowledge base
python3 research_agent/tools.py kb add --paper-id "2107.03006" --title "Title" --tags "diffusion,3D" --relevance-score 8.5
python3 research_agent/tools.py kb search --query "diffusion"
python3 research_agent/tools.py kb list
python3 research_agent/tools.py kb export
```

## Other Tools

| Directory | What |
|-----------|------|
| `research_agent/validate_debate.py` | Schema validator for debate log entries |
| `research_agent/tests/` | Tests for the debate validator |
| `research_agent/benchmarks/` | Benchmark suite for evaluating debate quality |
| `research_agent/debate_viz/` | HTML visualization for debate flows |

## File Structure

```
.claude/
  agents/                          # Agent definitions (the core of this system)
    research-paper-finder.md
    research-supervisor.md
    research-advocate-empiricist.md
    research-advocate-theorist.md
    research-advocate-contrarian.md
    research-falsifier.md
    meta-research-supervisor.md
    meta-advocate-*.md
    meta-research-falsifier.md
research_agent/
  tools.py                         # CLI tools (search, read, citations, kb, cache)
  validate_debate.py               # Debate log schema validator
  requirements.txt                 # Python deps (arxiv, pymupdf, httpx)
  tests/                           # Test suite
  benchmarks/                      # Debate quality benchmarks
  debate_viz/                      # HTML debate flow visualization
  CLAUDE.md                        # Agent conventions for this directory
CLAUDE.md                          # Root project config for Claude Code
```

## How the Debate System Prevents Bad Decisions

The three-advocate structure is designed so no single perspective can dominate:

- **Empiricist** grounds everything in data — no handwaving allowed
- **Theorist** demands mechanistic understanding — "it worked" isn't enough
- **Contrarian** prevents groupthink — must propose a concrete alternative, not just criticize

After two rounds of debate + cross-examination, the **Falsifier** stress-tests the winner against historical failure patterns, designs kill criteria for the first training run, and proposes the cheapest pre-test to validate the core assumption.
