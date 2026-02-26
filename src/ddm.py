"""Deterministic Delegation Model (DDM) implementation.

Core contribution of the paper. Treats delegation mandates as deterministic
function outputs rather than static tokens.

M = f(u, cap, r, ctx, p_v)
  u    = Principal (delegating user)
  cap  = Capability class
  r    = Target resource scope
  ctx  = Observable context
  p_v  = Versioned policy

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


@dataclass(frozen=True)
class Mandate:
    """A deterministic delegation mandate — derived artifact, not stored."""
    mandate_hash: str       # deterministic hash of inputs
    inputs: MandateInputs
    constraints: dict       # compiled constraints for enforcement
    issued_at: float        # timestamp
    expires_at: float       # TTL
    generation_latency_ms: float


@dataclass
class EnforcementResult:
    """Result of checking an execution request against a mandate."""
    allowed: bool
    mandate_hash: str
    violations: list[str]
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


@dataclass
class ResolutionResult:
    """Result of applying a Resolution Policy to a constraint conflict."""
    action: str             # "allow", "block", "substitute"
    selected_item: Optional[dict]  # DDM-selected item (None if block)
    relaxed_constraints: list[str]  # constraint names that were relaxed
    original_violations: list[str]  # violations detected by enforce()
    resolution_policy: str  # policy name that was applied
    satisfiable: bool       # whether original constraints were satisfiable


class DDM:
    """Deterministic Delegation Model — mandate generation and enforcement."""

    POLICY_VERSION = "v1.0.0"  # fixed for this experiment
    MANDATE_TTL_SECONDS = 300  # 5 minutes

    def __init__(self, principal: str = "experiment_user"):
        self.principal = principal
        self.audit_log: list[AuditRecord] = []

    def generate_mandate(self, scenario_constraints: dict) -> Mandate:
        """Generate a mandate deterministically from scenario constraints.

        This is the core DDM function: M = f(u, cap, r, ctx, p_v)
        Same inputs always produce the same mandate (except timestamps).
        """
        start = time.monotonic()
        now = time.time()

        inputs = MandateInputs(
            principal=self.principal,
            capability="commerce.purchase",
            resource_scope=self._compile_resource_scope(scenario_constraints),
            context={"generated_at_epoch": now},
            policy_version=self.POLICY_VERSION,
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
        }
        mandate_hash = hashlib.sha256(
            json.dumps(hash_input, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16]

        elapsed = (time.monotonic() - start) * 1000

        return Mandate(
            mandate_hash=mandate_hash,
            inputs=inputs,
            constraints=constraints,
            issued_at=now,
            expires_at=now + self.MANDATE_TTL_SECONDS,
            generation_latency_ms=elapsed,
        )

    def enforce(self, mandate: Mandate, purchase_request: dict) -> EnforcementResult:
        """Check a purchase request against a mandate. Fail-closed.

        purchase_request = {
            "items": [{"product_id": str, "quantity": int, "price": int,
                        "brand": str, "category": str, "rating": float}, ...]
        }
        """
        start = time.monotonic()
        violations = []
        items = purchase_request.get("items", [])
        constraints = mandate.constraints

        # Check expiry (fail-closed)
        if time.time() > mandate.expires_at:
            violations.append("MANDATE_EXPIRED")
            elapsed = (time.monotonic() - start) * 1000
            result = EnforcementResult(
                allowed=False, mandate_hash=mandate.mandate_hash,
                violations=violations, checked_at=time.time(),
                check_latency_ms=elapsed, request_summary=purchase_request,
            )
            self._record_audit(mandate, result)
            return result

        # Check category constraint
        if "category" in constraints:
            for item in items:
                if item.get("category", "").lower() != constraints["category"].lower():
                    violations.append(
                        f"CATEGORY_VIOLATION: {item.get('product_id')} "
                        f"is '{item.get('category')}', expected '{constraints['category']}'"
                    )

        # Check brand whitelist
        if "brand_whitelist" in constraints:
            allowed_brands = [b.lower() for b in constraints["brand_whitelist"]]
            for item in items:
                if item.get("brand", "").lower() not in allowed_brands:
                    violations.append(
                        f"BRAND_VIOLATION: {item.get('product_id')} "
                        f"brand '{item.get('brand')}' not in {constraints['brand_whitelist']}"
                    )

        # Check budget constraint
        if "max_budget" in constraints:
            total_price = sum(
                item.get("price", 0) * item.get("quantity", 1) for item in items
            )
            if total_price > constraints["max_budget"]:
                violations.append(
                    f"BUDGET_VIOLATION: total {total_price} USD "
                    f"exceeds limit {constraints['max_budget']} USD"
                )

        # Check quantity constraints
        total_qty = sum(item.get("quantity", 1) for item in items)
        if "max_quantity" in constraints and total_qty > constraints["max_quantity"]:
            violations.append(
                f"QUANTITY_VIOLATION: total quantity {total_qty} "
                f"exceeds max {constraints['max_quantity']}"
            )
        if "exact_quantity" in constraints and total_qty != constraints["exact_quantity"]:
            violations.append(
                f"QUANTITY_VIOLATION: total quantity {total_qty} "
                f"!= required {constraints['exact_quantity']}"
            )

        # Check rating constraint
        if "min_rating" in constraints:
            for item in items:
                if item.get("rating", 0) < constraints["min_rating"]:
                    violations.append(
                        f"RATING_VIOLATION: {item.get('product_id')} "
                        f"rating {item.get('rating')} < min {constraints['min_rating']}"
                    )

        # Check optimization (if required, verify it's the optimal choice)
        if "optimization" in constraints and constraints["optimization"] == "min_price":
            # This is checked post-hoc in the evaluator, not blocked here
            # DDM enforces hard constraints; optimization is a soft preference
            pass

        elapsed = (time.monotonic() - start) * 1000
        result = EnforcementResult(
            allowed=len(violations) == 0,
            mandate_hash=mandate.mandate_hash,
            violations=violations,
            checked_at=time.time(),
            check_latency_ms=elapsed,
            request_summary=purchase_request,
        )
        self._record_audit(mandate, result)
        return result

    def resolve(
        self,
        constraints: dict,
        catalog: list[dict],
        resolution_policy: str = "fail_closed",
    ) -> ResolutionResult:
        """Apply a Resolution Policy to determine a deterministic outcome.

        Given constraints and a catalog, compute whether the constraints are
        satisfiable. If not, apply the specified resolution policy:

        - fail_closed: block (no purchase)
        - priority_budget: relax lowest-priority constraints to satisfy budget first
        - priority_brand: relax lowest-priority constraints to satisfy brand first

        For priority_* policies, constraints are relaxed from lowest priority
        upward, and the cheapest satisfying item is selected.

        Returns a ResolutionResult with the deterministic outcome.
        """
        # Step 1: Find items satisfying ALL constraints
        satisfying = self._find_satisfying(catalog, constraints)

        if satisfying:
            # No conflict — pick cheapest among fully satisfying items
            best = min(satisfying, key=lambda p: p["price"])
            return ResolutionResult(
                action="allow",
                selected_item=best,
                relaxed_constraints=[],
                original_violations=[],
                resolution_policy=resolution_policy,
                satisfiable=True,
            )

        # Step 2: Constraints are unsatisfiable — determine violations
        violations = self._detect_violation_types(catalog, constraints)

        if resolution_policy == "fail_closed":
            return ResolutionResult(
                action="block",
                selected_item=None,
                relaxed_constraints=[],
                original_violations=violations,
                resolution_policy="fail_closed",
                satisfiable=False,
            )

        # Step 3: Priority-based relaxation
        priority_order = self._parse_priorities(resolution_policy, constraints)
        # Relax from lowest priority (end of list) upward
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
                return ResolutionResult(
                    action="substitute",
                    selected_item=best,
                    relaxed_constraints=relaxed,
                    original_violations=violations,
                    resolution_policy=resolution_policy,
                    satisfiable=False,
                )

        # Could not satisfy even after relaxing all non-priority constraints
        return ResolutionResult(
            action="block",
            selected_item=None,
            relaxed_constraints=relaxed,
            original_violations=violations,
            resolution_policy=resolution_policy,
            satisfiable=False,
        )

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
            if "max_quantity" in constraints:
                pass  # single-item check; quantity is always 1 in this context
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

    @staticmethod
    def _parse_priorities(policy: str, constraints: dict) -> list[str]:
        """Parse a resolution policy into a priority-ordered constraint list.

        Returns constraints ordered from highest to lowest priority.
        The resolve() method relaxes from the END (lowest priority) first.
        """
        # Map policy names to priority orderings
        # The first element is the highest priority (protected last)
        orderings = {
            "priority_budget": ["max_budget", "brand_whitelist", "min_rating", "category"],
            "priority_brand": ["brand_whitelist", "max_budget", "min_rating", "category"],
            "priority_brand_rating": ["brand_whitelist", "min_rating", "max_budget", "category"],
        }
        if policy in orderings:
            return orderings[policy]
        raise ValueError(f"Unknown resolution policy: {policy}")

    def verify_reproducibility(self, mandate: Mandate) -> tuple[bool, str]:
        """Re-generate mandate from stored inputs and verify hash matches.

        This is the key DDM property: any third party can reproduce the mandate.
        """
        # Reconstruct from the same inputs (excluding context timestamp)
        hash_input = {
            "principal": mandate.inputs.principal,
            "capability": mandate.inputs.capability,
            "resource_scope": mandate.inputs.resource_scope,
            "policy_version": mandate.inputs.policy_version,
            "constraints": mandate.constraints,
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
