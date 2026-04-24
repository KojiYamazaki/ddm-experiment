# Resolution Policies

Resolution Policies are first-class mandate components specifying agent behavior
under constraint conflict (see paper Section 4).

## Schema

### Type: fail_closed
Aborts execution when any delegated constraint is unsatisfiable.

```json
{"type": "fail_closed"}
```

### Type: relax
Sacrifices lower-priority constraints when conflicts arise.

```json
{"type": "relax", "method": "<method>", "priority": [...]}
```

**Fields:**
- `method`: relaxation method
  - `lexicographic`: priority-ordered relaxation. The constraint at `priority[0]`
    is protected most strongly; constraints are relaxed starting from `priority[-1]`.
- `priority`: ordered list of constraint type names, descending by protection priority.

## Mapping to Paper

| File | Paper reference | Description |
|---|---|---|
| `fail_closed.json` | Section 4, used in R4/R5/R6 | Block on any constraint violation |
| `priority_budget.json` | Section 6 Tables 2, 7 | Lexicographic relax with budget as top priority |
| `priority_brand.json` | Section 6 Table 2 | Lexicographic relax with brand as top priority |

## Future Extensions

The paper Section 4 architecturally defines additional policy types that are not
empirically validated in this paper (see Section 7 Limitations):

- `max_deviation` parameter for bounded relaxation (defined in Section 4)
- `type: negotiate(channel)` (defined in Section 4)
- `type: defer(condition)` (defined in Section 4)

These are intentionally not implemented in this artifact to keep the artifact
scope aligned with the paper's empirical claims.
