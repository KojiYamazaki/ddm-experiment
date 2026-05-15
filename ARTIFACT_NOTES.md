# Artifact Notes for AE Reviewers

See [README.md](README.md) for setup, reproduction paths, and the
paper reproduction map.

## Design note on product catalogs

The artifact contains two catalog sources. `data/catalog.json` (12 items)
is used by `dry_run.py` and `src/mock_api.py` for unit testing. The probe
scripts (R1–R7) each define an inline `EXTENDED_CATALOG` (13–21 items)
that includes additional products needed to create the constraint conflicts
studied in the paper (e.g., CAM-009 Panasonic at $310 for the T-brand-near-miss
scenario). The shared `EXTENDED_CATALOG` in `scripts/probe_utils.py` (13 items)
is the canonical catalog for R2–R7. R1 uses a larger variant (21 items) with
additional category-confusion products specific to its probe design.

## Note on stale values in results/probe_r7_results.json

The `ddm_canonical` block in `probe_r7_results.json` contains two known
stale values from an earlier code version:

- `selected_item_price: 21000` and `22000` (cent-denominated) instead of
  `210` and `220` (USD). The selected product IDs are correct.
- `relaxed: ["category", "brand_whitelist"]` includes `category`, which
  the current `_resolve` implementation no longer adds (category removal
  does not expand the candidate set for these scenarios). The selected
  products and resolution outcomes are unaffected.

These values are artifacts of the code version that generated the results.
The current code produces correct values if the R7 post-hoc step is re-run.

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
