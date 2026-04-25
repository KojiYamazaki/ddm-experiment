# Artifact Notes for AE Reviewers

See [README.md](README.md) for setup, reproduction paths, and the
paper reproduction map.

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
