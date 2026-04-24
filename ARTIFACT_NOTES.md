# Artifact Notes for AE Reviewers

This artifact corresponds to the ACM CAIS 2026 paper "Who Decides the
Trade-off? Resolution Policy as Delegation Governance in Autonomous Agents."

## Versioning

- **Tag `paper-experiments-as-run`**: DDM implementation at the time of
  paper experiments. Stored `mandate_hash` values in `results/probe_*.json`
  correspond to this version.
- **Tag `v1.0.0` (this version)**: AE submission version. Incorporates
  `resolution_policy` as an explicit input to the mandate hash, matching
  the formal definition M = f(u, cap, r, ctx, p_v, rp) in paper Section 4.
  This is a refactor for architectural clarity; no paper claims are affected.

## What `results/` contains

Pre-computed experimental results from the paper, generated with the
`paper-experiments-as-run` version. Each `results/probe_r*_results.json`
file contains the complete probe data for that round.

## What the refactor changed

The AE submission version incorporates Resolution Policy (rp) as a
first-class input to the mandate generation function, matching the
paper's formal definition in Section 4. This means:

1. Re-running experiments with `v1.0.0` will produce different
   `mandate_hash` values than those stored in `results/`.
2. Agent behavior, DDM decisions (enforce/resolve outcomes), and all
   statistical results are unchanged -- the refactor is a structural
   cleanup, not a behavioral change.
3. The paper's empirical claims (R1-R7) depend on determinism,
   non-bypassability, and prompt-independence -- not on specific
   hash values.

## Reproducing the paper

For the **Functional** badge (artifact works as described):

```bash
pip install -r requirements.txt
python scripts/dry_run.py                  # validate core logic (no API keys)
python scripts/probe_r4_ddm_posthoc.py     # example probe (requires API keys)
```

For the **Reproduced** badge (paper results are re-obtainable):
- Pre-computed results are in `results/`. Each file maps to a paper round.
- To re-run probes, execute the corresponding `scripts/probe_r*.py`.
- To reproduce the exact `mandate_hash` values in `results/`, check out
  the `paper-experiments-as-run` tag.
- With `v1.0.0`, re-running probes produces identical DDM decisions
  (same products selected, same violations detected) with updated
  hash values.

## Design note on constraint checking

DDM's constraint-checking logic is factored into a declarative rule table
(`CONSTRAINT_RULES` in `src/ddm.py`). Each rule specifies the item field to
check, comparison operator, scope (per-item or aggregate sum), and violation
message template.

In this artifact, `CONSTRAINT_RULES` is a class-level constant encoding the
schema of the `commerce.purchase` capability used in the paper's experiments.
This is a deliberate simplification consistent with the paper's scope: the
paper exercises a single capability domain, and Intent-to-Mandate conversion
(i.e., deriving rules from natural-language intent, or managing multiple
capability schemas) is explicitly left to future work (Section 7).

A production-grade DDM implementation would externalize constraint schemas as
per-capability definition files and compose them with principal intent at
mandate-generation time. That broader architecture is out of scope for this
artifact, which focuses on the paper's empirical claims.

## Script-to-paper mapping

| Script | Round | Paper reference |
|--------|-------|-----------------|
| `probe_r1.py` + `probe_r1_control.py` | R1 | Section 6.2: 1/108 deviation |
| `probe_r2.py` + `probe_r2_gpt52.py` | R2 | Section 6.2: stochastic resolution |
| `probe_r3.py` | R3 | Section 6.2: 76% to 0% deviation |
| `probe_r4_ddm_posthoc.py` + `_gpt52` | R4 | Section 6.4: VPR=100%, FRR=0% |
| `probe_r5_nonbypass.py` + `_gpt52` | R5 | Section 6.3, Table 5: 2x2 prompt x DDM |
| `probe_r6_injection.py` + `_gpt52` | R6 | Section 6.3, Table 6: 2x2 injection x DDM |
| `probe_r7_behavioral_resolution.py` | R7 | Section 6.4, Tables 7-8: behavioral resolution |
