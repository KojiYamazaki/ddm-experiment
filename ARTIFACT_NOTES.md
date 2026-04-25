# Artifact Notes for AE Reviewers

This artifact corresponds to the ACM CAIS 2026 paper "Who Decides the
Trade-off? Resolution Policy as Delegation Governance in Autonomous Agents."

## Reproducibility note

The mandate_hash values in `results/probe_*.json` were generated with
an earlier version of the DDM hash function that did not include the
Resolution Policy as an input.

The current code computes the mandate hash following the formal
definition M = f(u, cap, r, ctx, p_v, rp) (paper Section 4), which
includes the Resolution Policy. Re-running probes therefore produces
different mandate_hash values but identical DDM decisions (same products
selected, same violations detected).

LLM agent responses are stochastic (R2 explicitly studies this
phenomenon); aggregate statistics across re-runs are expected to
vary within sampling noise.

## Pre-computed results

`results/probe_r*_results.json` files contain complete probe data for each
round.

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

A generalization of DDM to arbitrary capability domains would externalize
constraint schemas and compose them with principal intent at mandate-generation
time. That broader architecture is out of scope for this artifact, which focuses
on the paper's empirical claims.

## Design note on the Audit Ledger

The DDM class exposes an in-memory audit interface (`_record_audit`,
`get_audit_log`) that records mandate generation, enforcement decisions,
and resolution outcomes during a probe execution. The paper (Section 5)
describes the Audit Ledger as "an append-only, cryptographically chained
log," and notes that "the experimental prototype implements the
deterministic mandate function and resolution enforcement---the variables
under evaluation---but omits cryptographic signing, as structural
determinism rather than non-repudiation is the property being tested."

Consistent with this scope, the artifact's audit log is not persisted
to disk and does not implement chaining or cryptographic operations.
Its purpose is to support inline inspection of DDM decisions during
probe execution; the empirical claims in Section 6 are validated through
probe result aggregates in `results/probe_*.json`, not through audit log
contents.

## Script-to-paper mapping

| Script | Round | Paper reference |
|--------|-------|-----------------|
| `probe_r1.py` + `probe_r1_control.py` | R1 | Section 6.2: 1/108 deviation |
| `probe_r2.py` + `probe_r2_gpt52.py` | R2 | Section 6.2: stochastic resolution |
| `probe_r3.py` | R3 | Section 6.2: 76% to 0% deviation |
| `probe_r4_ddm_posthoc.py` + `_gpt52` | R4 | Section 6.4: VPR=100%, FRR=0% |
| `probe_r5_nonbypass.py` + `_gpt52` | R5 | Section 6.3, Table 5: 2x2 prompt x DDM |
| `probe_r6_injection.py` + `_gpt52` | R6 | Section 6.3, Table 6: 2x2 injection x DDM |
| `probe_r7_behavioral_resolution.py` | R7 | Section 6.4, Tables 7-8: behavioral resolution. Table 7 row "A: bare" reuses R2 data (n=100); see README "Paper Reproduction Map" for details. |
