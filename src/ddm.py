"""Deterministic Delegation Model (DDM) implementation.

Core contribution of the paper. Treats delegation mandates as deterministic
function outputs rather than static tokens.

M = f(u, cap, r, ctx, p_v, rp)
  u    = Principal (delegating user)
  cap  = Capability class
  r    = Target resource scope
  ctx  = Observable context
  p_v  = Versioned policy
  rp   = Resolution policy

Properties:
  1. Reproducibility: same inputs → same mandate
  2. Non-authoritativeness: mandate is derived, not a source of authority
  3. Ephemerality: mandates are regenerated, not stored
  4. Fail-closed: no execution without a valid mandate
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Any


@dataclass(frozen=True)
class MandateInputs:
    """Observable inputs to the mandate generation function."""
    principal: str          # u: who is delegating
    capability: str         # cap: what class of action (e.g., "purchase")
    resource_scope: dict    # r: constraints on target resources
    context: dict           # ctx: observable context (e.g., timestamp, session)
    policy_version: str     # p_v: version-pinned policy identifier
    resolution_policy: dict # rp: resolution policy (see data/policies/)


@dataclass(frozen=True)
class Mandate:
    """A deterministic delegation mandate — derived artifact, not stored."""
    mandate_hash: str       # deterministic hash of inputs
    inputs: MandateInputs
    constraints: dict       # compiled constraints for enforcement
    resolution_policy: dict # rp: resolution policy for this mandate
    issued_at: float        # timestamp
    expires_at: float       # TTL
    generation_latency_ms: float


@dataclass
class EnforcementResult:
    """Result of the Compliance Gate checking an execution request against a mandate.

    The Compliance Gate validates the agent's proposed action, then applies
    the mandate's Resolution Policy if constraints are violated.
    """
    allowed: bool
    mandate_hash: str
    violations: list[str]       # constraint violations detected
    resolution_action: str      # "allow", "block", or "substitute"
    selected_item: Optional[dict]  # DDM-selected item (for substitute)
    relaxed_constraints: list[str] # constraints relaxed (for substitute)
    checked_at: float
    check_latency_ms: float
    request_summary: dict


@dataclass
class AuditRecord:
    """Complete audit trail entry for one enforcement decision."""
    mandate: dict
    enforcement: dict
    reproducible: bool      # can mandate be regenerated from inputs?
    reproduction_hash: Optional[str]  # hash from re-generation


class DDM:
    """Deterministic Delegation Model — mandate generation and enforcement.

    Usage:
        ddm = DDM(principal="user")
        mandate = ddm.generate_mandate(constraints, resolution_policy)
        result = ddm.enforce(mandate, purchase_request, catalog)

    The enforce() method is the single entry point for the Compliance Gate.
    It checks the agent's proposed action against the mandate's constraints,
    then applies the mandate's Resolution Policy to determine the outcome.
    """

    POLICY_VERSION = "v1.0.0"  # fixed for this experiment
    MANDATE_TTL_SECONDS = 300  # 5 minutes

    # Default resolution policy: fail_closed
    DEFAULT_RESOLUTION_POLICY = {"type": "fail_closed"}

    def __init__(self, principal: str = "experiment_user"):
        self.principal = principal
        self.audit_log: list[AuditRecord] = []

    def generate_mandate(
        self,
        scenario_constraints: dict,
        resolution_policy: Optional[dict] = None,
    ) -> Mandate:
        """Generate a mandate deterministically from scenario constraints.

        This is the core DDM function: M = f(u, cap, r, ctx, p_v, rp)
        Same inputs always produce the same mandate (except timestamps).

        Args:
            scenario_constraints: constraint definitions for enforcement
            resolution_policy: Resolution Policy dict (see data/policies/).
                Defaults to fail_closed if not specified.
        """
        if resolution_policy is None:
            resolution_policy = self.DEFAULT_RESOLUTION_POLICY

        start = time.monotonic()
        now = time.time()

        inputs = MandateInputs(
            principal=self.principal,
            capability="commerce.purchase",
            resource_scope=self._compile_resource_scope(scenario_constraints),
            context={"generated_at_epoch": now},
            policy_version=self.POLICY_VERSION,
            resolution_policy=resolution_policy,
        )

        # Compile enforcement constraints from inputs
        constraints = self._compile_constraints(scenario_constraints)

        # Deterministic hash (excluding timestamp for reproducibility check)
        hash_input = {
            "principal": inputs.principal,
            "capability": inputs.capability,
            "resource_scope": inputs.resource_scope,
            "policy_version": inputs.policy_version,
            "constraints": constraints,
            "resolution_policy": resolution_policy,
        }
        mandate_hash = hashlib.sha256(
            json.dumps(hash_input, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16]

        elapsed = (time.monotonic() - start) * 1000

        return Mandate(
            mandate_hash=mandate_hash,
            inputs=inputs,
            constraints=constraints,
            resolution_policy=resolution_policy,
            issued_at=now,
            expires_at=now + self.MANDATE_TTL_SECONDS,
            generation_latency_ms=elapsed,
        )

    def enforce(
        self,
        mandate: Mandate,
        purchase_request: dict,
        catalog: Optional[list[dict]] = None,
    ) -> EnforcementResult:
        """Compliance Gate: validate a purchase request against a mandate.

        This is the single entry point for DDM enforcement. It:
        1. Checks mandate expiry
        2. Checks the agent's proposed action against mandate constraints
        3. If no violations, allows the action
        4. If violations exist, delegates to _resolve which applies the
           mandate's Resolution Policy (enforce does not inspect RP type)

        Args:
            mandate: the delegation mandate
            purchase_request: agent's proposed action
                {"items": [{"product_id": str, "quantity": int, "price": int,
                            "brand": str, "category": str, "rating": float}, ...]}
            catalog: product catalog (passed to _resolve for relax policies)
        """
        start = time.monotonic()
        items = purchase_request.get("items", [])

        # Step 1: Check expiry
        if time.time() > mandate.expires_at:
            return self._make_result(
                start, mandate, purchase_request,
                allowed=False, violations=["MANDATE_EXPIRED"],
                resolution_action="block",
            )

        # Step 2: Check constraints
        violations = self._check_constraints(mandate.constraints, items)

        # Step 3: No violations — allow
        if not violations:
            return self._make_result(
                start, mandate, purchase_request,
                allowed=True, violations=[],
                resolution_action="allow",
            )

        # Step 4: Violations — delegate to Resolution Policy
        resolution = self._resolve(mandate.resolution_policy, mandate.constraints, catalog)
        return self._make_result(
            start, mandate, purchase_request,
            allowed=resolution["action"] != "block",
            violations=violations,
            resolution_action=resolution["action"],
            selected_item=resolution.get("selected_item"),
            relaxed_constraints=resolution.get("relaxed_constraints", []),
        )

    def _make_result(
        self, start: float, mandate: Mandate, purchase_request: dict, *,
        allowed: bool, violations: list[str], resolution_action: str,
        selected_item: Optional[dict] = None,
        relaxed_constraints: Optional[list[str]] = None,
    ) -> EnforcementResult:
        """Build an EnforcementResult and record the audit entry."""
        elapsed = (time.monotonic() - start) * 1000
        result = EnforcementResult(
            allowed=allowed, mandate_hash=mandate.mandate_hash,
            violations=violations,
            resolution_action=resolution_action,
            selected_item=selected_item,
            relaxed_constraints=relaxed_constraints or [],
            checked_at=time.time(), check_latency_ms=elapsed,
            request_summary=purchase_request,
        )
        self._record_audit(mandate, result)
        return result

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    # Declarative constraint rules. Each rule maps a constraint key to
    # its checking behavior. The _check_constraints method iterates this
    # table instead of hardcoding per-key logic.
    CONSTRAINT_RULES = [
        # per-item checks
        {"key": "category",       "field": "category", "op": "eq", "scope": "item",
         "case_insensitive": True, "default": "",
         "label": "CATEGORY_VIOLATION",
         "msg": "{pid} is '{actual}', expected '{expected}'"},
        {"key": "brand_whitelist", "field": "brand",   "op": "in", "scope": "item",
         "case_insensitive": True, "default": "",
         "label": "BRAND_VIOLATION",
         "msg": "{pid} brand '{actual}' not in {expected}"},
        {"key": "min_rating",     "field": "rating",   "op": "ge", "scope": "item",
         "default": 0,
         "label": "RATING_VIOLATION",
         "msg": "{pid} rating {actual} < min {expected}"},
        # aggregate checks
        {"key": "max_budget",     "field": "price",    "op": "le", "scope": "sum",
         "weight": "quantity", "default": 0,
         "label": "BUDGET_VIOLATION",
         "msg": "total {actual} USD exceeds limit {expected} USD"},
        {"key": "max_quantity",   "field": "quantity",  "op": "le", "scope": "sum",
         "default": 1,
         "label": "QUANTITY_VIOLATION",
         "msg": "total quantity {actual} exceeds max {expected}"},
        {"key": "exact_quantity", "field": "quantity",  "op": "eq", "scope": "sum",
         "default": 1,
         "label": "QUANTITY_VIOLATION",
         "msg": "total quantity {actual} != required {expected}"},
    ]

    # Comparison operators: returns True when constraint is SATISFIED
    _OPS = {
        "eq": lambda actual, expected: actual == expected,
        "in": lambda actual, expected: actual in expected,
        "ge": lambda actual, expected: actual >= expected,
        "le": lambda actual, expected: actual <= expected,
    }

    def _check_constraints(self, constraints: dict, items: list[dict]) -> list[str]:
        """Check all constraints against proposed items. Returns violation list.

        Iterates CONSTRAINT_RULES declaratively. Each rule specifies a
        constraint key, the item field to check, a comparison operator,
        and whether to check per-item or as an aggregate sum.
        """
        violations = []

        for rule in self.CONSTRAINT_RULES:
            key = rule["key"]
            if key not in constraints:
                continue

            expected = constraints[key]
            op_fn = self._OPS[rule["op"]]
            field = rule["field"]
            default = rule.get("default", 0)
            ci = rule.get("case_insensitive", False)

            if ci and rule["op"] != "in":
                expected = expected.lower() if isinstance(expected, str) else expected

            if rule["scope"] == "item":
                # Per-item: check each item individually
                if ci and rule["op"] == "in":
                    expected_normalized = [v.lower() for v in expected]
                else:
                    expected_normalized = expected

                for item in items:
                    actual = item.get(field, default)
                    actual_cmp = actual.lower() if ci and isinstance(actual, str) else actual

                    if not op_fn(actual_cmp, expected_normalized if rule["op"] == "in" else expected):
                        msg = self._format_violation(rule, item.get("product_id", ""), actual, expected)
                        violations.append(msg)

            elif rule["scope"] == "sum":
                # Aggregate: sum across all items, optionally weighted
                weight_field = rule.get("weight")
                if weight_field:
                    actual = sum(item.get(field, default) * item.get(weight_field, 1) for item in items)
                else:
                    actual = sum(item.get(field, default) for item in items)

                if not op_fn(actual, expected):
                    msg = self._format_violation(rule, "", actual, expected)
                    violations.append(msg)

        return violations

    @staticmethod
    def _format_violation(rule: dict, pid: str, actual, expected) -> str:
        """Format a violation message from a rule template.

        Uses safe formatting: only placeholders present in the template
        are substituted. Extra kwargs are silently ignored.
        """
        import string
        template = f"{rule['label']}: {rule['msg']}"
        formatter = string.Formatter()
        used_keys = {f for _, f, _, _ in formatter.parse(template) if f}
        kwargs = {"pid": pid, "actual": actual, "expected": expected}
        return template.format(**{k: v for k, v in kwargs.items() if k in used_keys})

    def _resolve(
        self,
        resolution_policy: dict,
        constraints: dict,
        catalog: Optional[list[dict]],
    ) -> dict:
        """Apply Resolution Policy to determine the outcome when constraints
        are violated.

        This method owns all RP-type-specific logic. The caller (enforce)
        does not inspect the RP type.

        Returns dict with keys: action, selected_item, relaxed_constraints.
        """
        policy_type = resolution_policy.get("type", "fail_closed")

        if policy_type == "fail_closed":
            return {"action": "block", "selected_item": None, "relaxed_constraints": []}

        # All non-fail_closed policies require a catalog
        if catalog is None:
            return {"action": "block", "selected_item": None, "relaxed_constraints": []}

        # relax — lexicographic priority-based relaxation
        priority_order = resolution_policy.get("priority", [])
        relaxed = []
        current_constraints = dict(constraints)

        for constraint_name in reversed(priority_order):
            if constraint_name not in current_constraints:
                continue
            relaxed.append(constraint_name)
            del current_constraints[constraint_name]

            candidates = self._find_satisfying(catalog, current_constraints)
            if candidates:
                best = min(candidates, key=lambda p: p["price"])
                return {"action": "substitute", "selected_item": best, "relaxed_constraints": relaxed}

        # Could not satisfy even after relaxing all
        return {"action": "block", "selected_item": None, "relaxed_constraints": relaxed}

    def _find_satisfying(self, catalog: list[dict], constraints: dict) -> list[dict]:
        """Return catalog items that satisfy all given constraints."""
        results = []
        for item in catalog:
            if not item.get("in_stock", True):
                continue
            if "category" in constraints:
                if item.get("category", "").lower() != constraints["category"].lower():
                    continue
            if "brand_whitelist" in constraints:
                allowed = [b.lower() for b in constraints["brand_whitelist"]]
                if item.get("brand", "").lower() not in allowed:
                    continue
            if "max_budget" in constraints:
                if item.get("price", 0) > constraints["max_budget"]:
                    continue
            if "min_rating" in constraints:
                if item.get("rating", 0) < constraints["min_rating"]:
                    continue
            results.append(item)
        return results

    def _detect_violation_types(self, catalog: list[dict], constraints: dict) -> list[str]:
        """Detect which constraint types cause unsatisfiability."""
        violations = []
        constraint_keys = ["max_budget", "brand_whitelist", "min_rating", "category"]
        for key in constraint_keys:
            if key not in constraints:
                continue
            relaxed = {k: v for k, v in constraints.items() if k != key}
            if self._find_satisfying(catalog, relaxed):
                label = {
                    "max_budget": "BUDGET",
                    "brand_whitelist": "BRAND",
                    "min_rating": "RATING",
                    "category": "CATEGORY",
                }.get(key, key)
                violations.append(label)
        return violations

    def verify_reproducibility(self, mandate: Mandate) -> tuple[bool, str]:
        """Re-generate mandate from stored inputs and verify hash matches.

        This is the key DDM property: any third party can reproduce the
        mandate from its stored inputs using the current DDM implementation.

        Note on mandate_hash values in results/:
        The `mandate_hash` values in `results/probe_*.json` were
        generated with an earlier hash function that did not include
        the Resolution Policy as an input. The current implementation
        includes resolution_policy per M = f(u, cap, r, ctx, p_v, rp)
        in paper Section 4. Re-running produces different hash values
        but identical DDM decisions.
        """
        hash_input = {
            "principal": mandate.inputs.principal,
            "capability": mandate.inputs.capability,
            "resource_scope": mandate.inputs.resource_scope,
            "policy_version": mandate.inputs.policy_version,
            "constraints": mandate.constraints,
            "resolution_policy": mandate.resolution_policy,
        }
        reproduced_hash = hashlib.sha256(
            json.dumps(hash_input, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16]
        return reproduced_hash == mandate.mandate_hash, reproduced_hash

    def _compile_resource_scope(self, constraints: dict) -> dict:
        """Compile resource scope from scenario constraints."""
        scope = {}
        if "category" in constraints:
            scope["category"] = constraints["category"]
        if "brand_whitelist" in constraints:
            scope["brands"] = constraints["brand_whitelist"]
        return scope

    def _compile_constraints(self, scenario_constraints: dict) -> dict:
        """Compile enforcement constraints from scenario definition.

        This is a deterministic transformation — no LLM involved.
        """
        compiled = {}
        direct_keys = [
            "max_budget", "currency", "category", "max_quantity",
            "exact_quantity", "min_rating", "brand_whitelist", "optimization",
            "budget_is_total",
        ]
        for key in direct_keys:
            if key in scenario_constraints:
                compiled[key] = scenario_constraints[key]
        return compiled

    def _record_audit(self, mandate: Mandate, result: EnforcementResult):
        """Record an audit entry."""
        reproducible, repro_hash = self.verify_reproducibility(mandate)
        self.audit_log.append(AuditRecord(
            mandate={
                "hash": mandate.mandate_hash,
                "principal": mandate.inputs.principal,
                "capability": mandate.inputs.capability,
                "constraints": mandate.constraints,
                "resolution_policy": mandate.resolution_policy,
                "issued_at": mandate.issued_at,
                "expires_at": mandate.expires_at,
            },
            enforcement=asdict(result),
            reproducible=reproducible,
            reproduction_hash=repro_hash,
        ))

    def get_audit_log(self) -> list[dict]:
        """Return audit log as serializable dicts."""
        return [asdict(r) for r in self.audit_log]

    def reset(self):
        """Reset audit log for next trial."""
        self.audit_log.clear()
