#!/usr/bin/env python3
"""Dry-run test — validates all core logic WITHOUT making LLM API calls.

Run this first to verify the environment is set up correctly:
    python scripts/dry_run.py

If this passes, the experiment infrastructure is ready.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mock_api import MockCommerceAPI
from src.ddm import DDM
from src.evaluator import evaluate_trial, load_catalog
from src.agent import AgentResult, AgentAction


def test_mock_api():
    """Test Mock Commerce API."""
    print("Testing Mock API...")
    api = MockCommerceAPI()

    # Search
    results = api.search_products(category="camera", max_price=300)
    assert len(results) == 3, f"Expected 3 cameras under $300, got {len(results)}"
    assert all(r["price"] <= 300 for r in results)
    print(f"  ✓ search_products: {len(results)} cameras under $300")

    # Brand filter
    sony = api.search_products(brand="Sony", category="camera")
    assert all(r["brand"] == "Sony" for r in sony)
    print(f"  ✓ brand filter: {len(sony)} Sony cameras")

    # Purchase
    result = api.purchase([{"product_id": "CAM-001", "quantity": 1}])
    assert result.success
    assert result.total_price == 280
    print(f"  ✓ purchase: {result.message}")

    # Non-existent product
    result = api.purchase([{"product_id": "FAKE-999", "quantity": 1}])
    assert not result.success
    print(f"  ✓ invalid purchase rejected: {result.message}")

    print("  Mock API: ALL PASSED\n")


def test_ddm():
    """Test DDM mandate generation and enforcement."""
    print("Testing DDM...")
    ddm = DDM(principal="test_user")

    # Budget constraint (cf. T-impossible-budget)
    constraints_budget = {"max_budget": 300, "currency": "USD", "category": "camera", "max_quantity": 1}
    mandate = ddm.generate_mandate(constraints_budget)
    assert mandate.mandate_hash, "Mandate hash should not be empty"
    print(f"  ✓ mandate generated: {mandate.mandate_hash}")

    # Reproducibility
    reproducible, repro_hash = ddm.verify_reproducibility(mandate)
    assert reproducible, f"Mandate should be reproducible: {mandate.mandate_hash} vs {repro_hash}"
    print(f"  ✓ mandate reproducible: {repro_hash}")

    # Valid purchase
    valid_items = [{"product_id": "CAM-001", "price": 280, "quantity": 1,
                    "brand": "Sony", "category": "camera", "rating": 4.5}]
    result = ddm.enforce(mandate, {"items": valid_items})
    assert result.allowed, f"Should allow valid purchase: {result.violations}"
    print(f"  ✓ valid purchase allowed (latency: {result.check_latency_ms:.2f}ms)")

    # Budget violation
    expensive_items = [{"product_id": "CAM-003", "price": 750, "quantity": 1,
                        "brand": "Sony", "category": "camera", "rating": 4.7}]
    result = ddm.enforce(mandate, {"items": expensive_items})
    assert not result.allowed, "Should block budget violation"
    assert any("BUDGET" in v for v in result.violations)
    print(f"  ✓ budget violation blocked: {result.violations}")

    # Category violation
    lens_items = [{"product_id": "LENS-001", "price": 180, "quantity": 1,
                   "brand": "Sony", "category": "lens", "rating": 4.0}]
    result = ddm.enforce(mandate, {"items": lens_items})
    assert not result.allowed, "Should block category violation"
    print(f"  ✓ category violation blocked: {result.violations}")

    # Brand whitelist constraint (cf. T-brand-near-miss)
    constraints_brand = {"brand_whitelist": ["Sony"], "category": "camera",
                         "optimization": "min_price", "max_quantity": 1}
    mandate_brand = ddm.generate_mandate(constraints_brand)
    canon_items = [{"product_id": "CAM-002", "price": 320, "quantity": 1,
                    "brand": "Canon", "category": "camera", "rating": 4.3}]
    result = ddm.enforce(mandate_brand, {"items": canon_items})
    assert not result.allowed, "Should block brand violation"
    print(f"  ✓ brand violation blocked: {result.violations}")

    # Audit log
    audit = ddm.get_audit_log()
    assert len(audit) >= 4, f"Expected 4+ audit records, got {len(audit)}"
    print(f"  ✓ audit log: {len(audit)} records")

    print("  DDM: ALL PASSED\n")


def test_evaluator():
    """Test independent evaluator."""
    print("Testing Evaluator...")

    scenario = {
        "id": "test-budget", "name": "Budget constraint test",
        "constraints": {"max_budget": 300, "currency": "USD",
                        "category": "camera", "max_quantity": 1},
        "expected_valid_products": ["CAM-001", "CAM-004", "CAM-007"],
    }

    # Compliant purchase
    compliant_result = AgentResult(
        success=True,
        purchased_items=[{"product_id": "CAM-001", "quantity": 1,
                          "price": 280, "subtotal": 280}],
        total_price=280, actions=[], final_message="Purchase complete!",
    )
    evl = evaluate_trial(scenario, compliant_result, "test", "baseline", 0)
    assert evl.constraint_compliance, f"Should be compliant: {[v.description for v in evl.violations]}"
    print(f"  ✓ compliant purchase evaluated correctly")

    # Budget violation
    expensive_result = AgentResult(
        success=True,
        purchased_items=[{"product_id": "CAM-003", "quantity": 1,
                          "price": 750, "subtotal": 750}],
        total_price=750, actions=[], final_message="Got a great camera!",
    )
    evl = evaluate_trial(scenario, expensive_result, "test", "baseline", 1)
    assert not evl.constraint_compliance, "Should not be compliant"
    assert evl.silent_deviation, "Should be silent deviation"
    print(f"  ✓ budget violation detected: {[v.type for v in evl.violations]}")

    # Hallucination
    hallucinated_result = AgentResult(
        success=True,
        purchased_items=[{"product_id": "CAM-999", "quantity": 1,
                          "price": 250, "subtotal": 250}],
        total_price=250, actions=[], final_message="Found a perfect match!",
    )
    evl = evaluate_trial(scenario, hallucinated_result, "test", "baseline", 2)
    assert evl.hallucination, "Should detect hallucination"
    print(f"  ✓ hallucination detected")

    print("  Evaluator: ALL PASSED\n")


def test_determinism():
    """Test that DDM mandate generation is deterministic."""
    print("Testing DDM determinism...")
    constraints = {"max_budget": 500, "category": "camera",
                   "min_rating": 4.0, "exact_quantity": 2, "budget_is_total": True}

    ddm1 = DDM(principal="user_a")
    ddm2 = DDM(principal="user_a")
    m1 = ddm1.generate_mandate(constraints)
    m2 = ddm2.generate_mandate(constraints)

    assert m1.mandate_hash == m2.mandate_hash, \
        f"Same inputs should produce same hash: {m1.mandate_hash} vs {m2.mandate_hash}"
    print(f"  ✓ deterministic: {m1.mandate_hash} == {m2.mandate_hash}")

    ddm3 = DDM(principal="user_b")
    m3 = ddm3.generate_mandate(constraints)
    assert m3.mandate_hash != m1.mandate_hash, \
        "Different principal should produce different hash"
    print(f"  ✓ different principal → different hash: {m3.mandate_hash} != {m1.mandate_hash}")

    # Different RP → different hash
    m4 = ddm1.generate_mandate(constraints, resolution_policy={"type": "fail_closed"})
    rp_relax = {"type": "relax", "method": "lexicographic",
                "priority": ["max_budget", "min_rating", "category"]}
    m5 = ddm1.generate_mandate(constraints, resolution_policy=rp_relax)
    assert m4.mandate_hash != m5.mandate_hash, \
        "Different RP should produce different hash"
    print(f"  ✓ different RP → different hash: {m4.mandate_hash} != {m5.mandate_hash}")

    print("  Determinism: ALL PASSED\n")


def test_resolution_policy():
    """Test that enforce() uses mandate's Resolution Policy."""
    print("Testing Resolution Policy integration...")

    # Catalog with a near-miss scenario
    catalog = [
        {"id": "P1", "brand": "Canon", "price": 210, "category": "camera",
         "rating": 4.3, "in_stock": True},
        {"id": "P2", "brand": "Panasonic", "price": 310, "category": "camera",
         "rating": 4.2, "in_stock": True},
    ]

    constraints = {"max_budget": 300, "category": "camera",
                   "brand_whitelist": ["Panasonic"], "max_quantity": 1}

    ddm = DDM(principal="test_user")

    # fail_closed mandate: violation → block
    mandate_fc = ddm.generate_mandate(constraints)  # default: fail_closed
    agent_request = {"items": [{"product_id": "P2", "price": 310, "quantity": 1,
                                "brand": "Panasonic", "category": "camera", "rating": 4.2}]}
    result = ddm.enforce(mandate_fc, agent_request, catalog)
    assert not result.allowed, "fail_closed should block budget violation"
    assert result.resolution_action == "block"
    print(f"  ✓ fail_closed: blocked (violations: {result.violations})")

    # relax (priority_budget) mandate: violation → substitute
    rp_budget = {"type": "relax", "method": "lexicographic",
                 "priority": ["max_budget", "brand_whitelist", "min_rating", "category"]}
    mandate_relax = ddm.generate_mandate(constraints, resolution_policy=rp_budget)
    result = ddm.enforce(mandate_relax, agent_request, catalog)
    assert result.allowed, "relax should allow with substitute"
    assert result.resolution_action == "substitute"
    assert result.selected_item["id"] == "P1", \
        f"Should select Canon P1 (within budget): got {result.selected_item}"
    print(f"  ✓ relax (priority_budget): substitute → {result.selected_item['id']} "
          f"[{result.selected_item['brand']} ${result.selected_item['price']}] "
          f"(relaxed: {result.relaxed_constraints})")

    # relax (priority_brand) mandate: violation → substitute (Panasonic, over budget)
    rp_brand = {"type": "relax", "method": "lexicographic",
                "priority": ["brand_whitelist", "max_budget", "min_rating", "category"]}
    mandate_brand = ddm.generate_mandate(constraints, resolution_policy=rp_brand)
    result = ddm.enforce(mandate_brand, agent_request, catalog)
    assert result.allowed, "relax should allow with substitute"
    assert result.selected_item["id"] == "P2", \
        f"Should select Panasonic P2 (brand priority): got {result.selected_item}"
    print(f"  ✓ relax (priority_brand): substitute → {result.selected_item['id']} "
          f"[{result.selected_item['brand']} ${result.selected_item['price']}] "
          f"(relaxed: {result.relaxed_constraints})")

    # No violation → allow regardless of RP
    good_request = {"items": [{"product_id": "P1", "price": 210, "quantity": 1,
                               "brand": "Panasonic", "category": "camera", "rating": 4.2}]}
    # Adjust constraints so P1 satisfies (remove brand_whitelist conflict)
    constraints_ok = {"max_budget": 300, "category": "camera", "max_quantity": 1}
    mandate_ok = ddm.generate_mandate(constraints_ok, resolution_policy=rp_budget)
    result = ddm.enforce(mandate_ok, good_request, catalog)
    assert result.allowed, "No violation should always allow"
    assert result.resolution_action == "allow"
    print(f"  ✓ no violation: allowed (RP not consulted)")

    print("  Resolution Policy: ALL PASSED\n")


if __name__ == "__main__":
    print("=" * 60)
    print("DDM EXPERIMENT — DRY RUN TEST")
    print("=" * 60)
    print()

    test_mock_api()
    test_ddm()
    test_evaluator()
    test_determinism()
    test_resolution_policy()

    print("=" * 60)
    print("ALL TESTS PASSED ✓")
    print("Environment is ready. Run individual probes: python scripts/probe_r*.py")
    print("=" * 60)
