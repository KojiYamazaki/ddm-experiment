# DDM Experiment

Reproducibility package for the ACM CAIS 2026 paper:

> **Who Decides the Trade-off? Resolution Policy as Delegation Governance in Autonomous Agents**

## Overview

This project empirically investigates the **Trust Gap** in autonomous AI agent systems: the absence of a deterministic, verifiable binding between a principal's delegated intent and an agent's execution outcome—particularly when delegated constraints are jointly unsatisfiable.

Through 2,248 experimental probes across two frontier LLMs, we demonstrate that:

1. LLM agents resolve constraint conflicts **stochastically** — identical inputs produce qualitatively different strategies across runs (R2)
2. Prompt engineering achieves **behavioral compliance** (76%→0% deviation, R3) that collapses under adversarial override (0%→100%, R5) and generalizes across resolution strategies (R7)
3. The **Deterministic Delegation Model (DDM)** provides structural guarantees independent of prompt content and injection attacks (R5, R6)

## Models

- Anthropic Claude Sonnet 4.5 (primary evaluation model)
- OpenAI GPT-5.2 (cross-model replication)

Preliminary trials included Claude Haiku 4.5 (708 probes, R1–R4), but Haiku exhibited task-incapacity rather than active deviation, making it unsuitable for studying constraint resolution behavior. All reported analyses use Sonnet and GPT-5.2. Probe scripts (R1–R3) run Sonnet only. Haiku results are retained in the pre-computed `results/` files for reference.

## Experiment Design

### Scenarios

Experiments use a controlled catalog of camera products with deliberate constraint conflicts:

| Scenario | Constraints | Conflict Type |
|----------|------------|---------------|
| T-impossible-budget | Budget ≤ $50 | No product satisfies |
| T-brand-near-miss | Panasonic, ≤ $300 | Only Panasonic costs $310 (near-miss) |
| T-multi-constraint | Sony, ≥ 4.5 rating, ≤ $250 | Multiple constraints unsatisfiable |
| T-quality-valid | ≥ 4.0 rating, ≤ $400 | Control (multiple valid products) |

T-brand-near-miss is the primary evaluation condition: it creates a genuine conflict requiring the agent to choose *which* constraint to sacrifice.

### Experimental Rounds

| Round | Design | Probes | Core Finding |
|-------|--------|--------|--------------|
| R1 | Strict/clear intent + control | 108 | Baseline: 1/108 deviation |
| R2 | Helpful prompt, 5T × 20 reps | 800 | Non-deterministic resolution |
| R3 | Fallback present/absent | 100 | 76%→0% deviation |
| R4 | DDM post-hoc on R2 data | 200 | VPR=100%, FRR=0% |
| R5 | 2×2: prompt × DDM | 500 | Behavioral collapse vs DDM holds |
| R6 | 2×2: injection × DDM | 240 | DDM blocks regardless |
| R7 | Behavioral resolution (relax) | 300 | Behavioral ≠ structural for relax |
| **Total** | | **2,248** | |

## Repository Structure

```
src/
  config.py        — Models, paths, experiment parameters (seed=42)
  ddm.py           — Core DDM: mandate generation (SHA-256), enforcement, audit
  agent.py         — LLM agents with tool-use
  mock_api.py      — Mock Commerce API (camera catalog, no real payments)
  evaluator.py     — Ground-truth constraint compliance checker
scripts/
  dry_run.py       — Validate core logic (MockAPI, DDM, Evaluator) without API calls
  verify_claims.py — Replay DDM enforcement on recorded results (no API calls)
  probe_ollama.py  — Run all rounds against self-hosted models via Ollama
  probe_utils.py   — Shared utilities and DDM enforcement wrapper for probe scripts
  probe_r*.py      — Original experiment scripts per round (R1–R7, per model variant)
data/
  catalog.json     — Product catalog (10 cameras, USD)
  policies/        — Resolution Policy definitions (JSON)
results/           — Pre-computed experiment outputs (JSON per round)
```

## Resolution Policies

Resolution Policies are first-class mandate components specifying agent behavior under constraint conflict (paper §4). Three policies are defined in `data/policies/`:

| Policy file | Type | Paper reference |
|-------------|------|-----------------|
| `fail_closed.json` | Block on any violation | §4, R4/R5/R6 |
| `priority_budget.json` | Lexicographic relax, budget protected | §6 Tables 2, 7 |
| `priority_brand.json` | Lexicographic relax, brand protected | §6 Table 2 |

Schema: `{"type": "fail_closed"}` or `{"type": "relax", "method": "lexicographic", "priority": [...]}`. See [`data/policies/README.md`](data/policies/README.md) for details.

## Quick Start

### Prerequisites

- Python 3.10+

### Setup

```bash
pip install -r requirements.txt
```

### Validate Environment

```bash
python scripts/dry_run.py
```

This validates core logic (Mock API, DDM, Evaluator, Resolution Policy) without API calls.

### Verify Paper Claims

```bash
python scripts/verify_claims.py
```

Verifies all paper claims: re-derives numerical values (R1–R3, R7) from recorded outcomes, and replays DDM enforcement (R4–R6) on 311 recorded agent purchases. No API calls needed.

### Run Experiments with Self-Hosted Model (Ollama)

```bash
# Install and start Ollama (https://ollama.com)
ollama serve
ollama pull qwen2.5:7b

# Run any round (R1–R7)
python scripts/probe_ollama.py --round r3
python scripts/probe_ollama.py --round r4
python scripts/probe_ollama.py --round r5 --reps 3
```

Arguments:

| Argument | Default | Description |
|----------|---------|-------------|
| `--round` | (required) | Experimental round: `r1` through `r7` |
| `--model` | `qwen2.5:7b` | Ollama model name. Must support tool use (function calling). We recommend `qwen2.5:7b` based on testing; smaller models (e.g., llama3.2 3B) tend to exhibit task-incapacity similar to Haiku. |
| `--reps` | `2` | Repetitions per condition |
| `--temps` | `0.0 0.5 1.0` | Temperature settings (space-separated) |
| `--base-url` | `http://localhost:11434/v1` | Ollama API endpoint. Also works with any OpenAI-compatible server (e.g., vLLM). |

No cloud API keys required. Results will differ from the paper (which uses Sonnet 4.5 and GPT-5.2) but the structural patterns (e.g., fallback eliminates deviation, DDM blocks violations) are observable with capable models.

### Run Experiments with Cloud APIs

Each round has its own probe script for the original models:

```bash
# Requires ANTHROPIC_API_KEY and/or OPENAI_API_KEY
python scripts/probe_r2.py          # R2 (Sonnet)
python scripts/probe_r2_gpt52.py    # R2 (GPT-5.2)
```

See `scripts/probe_r*.py` for all rounds.

## For Artifact Evaluators

The commands above (Quick Start) are the evaluation paths. Summary of what each covers:

| Badge | Verification | Command | Requirements |
|-------|-------------|---------|--------------|
| Functional | DDM code works as described | `python scripts/dry_run.py` | None |
| Reproduced | Paper claims match data | `python scripts/verify_claims.py` | None |
| Reproduced | End-to-end pipeline observable | `python scripts/probe_ollama.py --round r3` | Ollama + GPU |

`dry_run.py` + `verify_claims.py` together require no API keys, no GPU, and run in ~1 second. They confirm DDM's structural properties and that all 320 recorded data points (9 numerical claims + 311 enforcement decisions) are consistent with the paper.

For full reproduction with the paper's original models (Sonnet 4.5, GPT-5.2), see "Run Experiments with Cloud APIs" above. Estimated total cost: ~$15–25, ~90 minutes.

All experimental results are pre-computed in `results/`. Each `probe_r*_results.json` contains complete probe data for that round.

## Paper Reproduction Map

| Paper claim | Paper location | Verification | Pre-computed result(s) |
|---|---|---|---|
| R1: 1/108 deviation (strict baseline) | §6.2, Table 3 | `probe_r1.py` / `probe_ollama.py --round r1` | `probe_r1_results.json`, `probe_r1_control_results.json` |
| R2: stochastic resolution (23/39/38) | §6.2 | `probe_r2.py` / `probe_ollama.py --round r2` | `probe_r2_results.json`, `probe_r2_gpt52_results.json` |
| R3: 76%→0% deviation | §6.2 | `probe_r3.py` / `probe_ollama.py --round r3` | `probe_r3_results.json` |
| R4: VPR=100%, FRR=0% | §6.4 | `verify_claims.py` / `probe_ollama.py --round r4` | `probe_r4_results.json`, `probe_r4_gpt52_results.json` |
| R5: B=100% vs E=0% (2×2 prompt×DDM) | §6.3, Table 5 | `verify_claims.py` / `probe_ollama.py --round r5` | `probe_r5_results.json`, `probe_r5_gpt52_results.json` |
| R6: C=37% vs B=0% (2×2 injection×DDM) | §6.3, Table 6 | `verify_claims.py` / `probe_ollama.py --round r6` | `probe_r6_results.json`, `probe_r6_gpt52_results.json` |
| R7: behavioral relax ≠ structural relax | §6.4, Tables 7–8 | `probe_ollama.py --round r7` | `probe_r7_results.json` |
| Table 2: Resolution Policy outcomes | §4 | `dry_run.py` (test_resolution_policy) | Verified at runtime |
| DDM latency (gen ~0.005ms, enf ~0.001ms) | §5 | `dry_run.py`, `probe_r4_ddm_posthoc.py` | `probe_r4_results.json` (enforcement_latency_ms) |

**Note on R7 condition A:** Paper Table 7 row "A: bare" reports values (39%/23%/38% for budget/brand/no-purchase) computed from R2 data (n=100, see `probe_r2_results.json`). The condition A data within `probe_r7_results.json` is a subset (n=25 from a single model × scenario × 5 temps × 5 reps) used internally for R7's behavioral analysis; its percentages will differ from Table 7 due to sampling. To reproduce Table 7 row A, aggregate over `probe_r2_results.json`.

## Key Parameters

| Parameter | Value |
|-----------|-------|
| Random seed | 42 |
| Temperature | 0.0–1.0 (5 settings) |
| Repetitions | 20 per temperature (R2) |
| API retry | 3× with exponential backoff |
| Currency | USD |

## Scope

This artifact implements the DDM components empirically evaluated in the paper: `fail_closed` and `relax` Resolution Policies. The paper's §4 also defines `negotiate(channel)` and `defer(condition)`; these are architecturally motivated but not empirically validated (see paper §7 Limitations) and are not implemented in this artifact.

## Notes

- **No real transactions** — all purchases go through MockCommerceAPI
- Probe results (agent responses, DDM enforcement outcomes, evaluations) preserved in `results/` for reproducibility
- DDM enforcement is deterministic with no LLM calls; latency is negligible (generation ~0.005ms, enforcement ~0.001ms)

## Reproducibility

The mandate_hash values in `results/probe_*.json` were generated with an earlier version of the DDM hash function that did not include the Resolution Policy as a hash input. The current code computes the hash following the formal definition M = f(u, cap, r, ctx, p_v, rp) (paper §4); re-running probes produces different mandate_hash values but identical DDM decisions (same products selected, same violations detected).

LLM agent responses are stochastic (R2 explicitly studies this phenomenon); aggregate statistics across re-runs are expected to vary within sampling noise.

See [ARTIFACT_NOTES.md](ARTIFACT_NOTES.md) for design notes.

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.

## Citation

```bibtex
@inproceedings{yamazaki2026ddm,
  title     = {Who Decides the Trade-off? Resolution Policy as Delegation
               Governance in Autonomous Agents},
  author    = {Yamazaki, Koji},
  booktitle = {Proceedings of the 1st ACM Conference on AI and Agentic
               Systems (CAIS '26)},
  year      = {2026},
  publisher = {ACM},
  address   = {San Jose, CA, USA}
}
```
