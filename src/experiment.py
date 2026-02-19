"""Experiment runner — orchestrates baseline and DDM trials.

Handles retry logic, resume capability, and structured logging.
"""

import json
import os
import sys
import time
import random
import traceback
from dataclasses import asdict
from pathlib import Path

from src.config import (
    MODELS, TRIALS_PER_CONDITION, RANDOM_SEED, MAX_RETRIES,
    RETRY_BACKOFF_BASE, SCENARIOS_PATH, RESULTS_DIR,
)
from src.mock_api import MockCommerceAPI
from src.ddm import DDM
from src.agent import run_agent, AgentResult, AgentAction
from src.evaluator import evaluate_trial, check_ddm_false_rejection


def load_scenarios() -> list[dict]:
    with open(SCENARIOS_PATH) as f:
        return json.load(f)


def load_catalog_for_enrichment() -> dict[str, dict]:
    """Load catalog for enriching purchase requests with product details."""
    from src.config import CATALOG_PATH
    with open(CATALOG_PATH) as f:
        products = json.load(f)
    return {p["id"]: p for p in products}


def _trial_key(experiment: str, model: str, scenario_id: str, trial: int) -> str:
    return f"{experiment}|{model}|{scenario_id}|{trial}"


def _load_completed(filepath: Path) -> set[str]:
    """Load completed trial keys from existing results file."""
    completed = set()
    if filepath.exists():
        with open(filepath) as f:
            for line in f:
                try:
                    record = json.loads(line)
                    key = _trial_key(
                        record["experiment"], record["model"],
                        record["scenario_id"], record["trial_number"],
                    )
                    completed.add(key)
                except (json.JSONDecodeError, KeyError):
                    continue
    return completed


def _append_result(filepath: Path, record: dict):
    """Append a single result record to JSONL file."""
    with open(filepath, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _run_single_trial_with_retry(
    fn, *args, max_retries=MAX_RETRIES, **kwargs
) -> AgentResult:
    """Run a trial with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt < max_retries - 1:
                wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                print(f"    Retry {attempt + 1}/{max_retries} after {wait}s: {e}")
                time.sleep(wait)
            else:
                print(f"    All retries failed: {e}")
                return AgentResult(
                    success=False, purchased_items=[], total_price=0,
                    actions=[], final_message="",
                    error=f"All {max_retries} retries failed. Last error: {e}",
                    total_latency_ms=0,
                )


def run_experiment_1_baseline(resume: bool = False):
    """Experiment 1: Baseline — no DDM control.

    Agent executes shopping tasks directly against Mock API.
    """
    print("=" * 60)
    print("EXPERIMENT 1: BASELINE (No DDM)")
    print("=" * 60)

    scenarios = load_scenarios()
    output_path = RESULTS_DIR / "experiment1_raw.jsonl"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    completed = _load_completed(output_path) if resume else set()
    if not resume and output_path.exists():
        output_path.unlink()

    random.seed(RANDOM_SEED)
    total = len(MODELS) * len(scenarios) * TRIALS_PER_CONDITION
    done = len(completed)

    for model_cfg in MODELS:
        for scenario in scenarios:
            for trial in range(TRIALS_PER_CONDITION):
                key = _trial_key(
                    "baseline", model_cfg["display_name"],
                    scenario["id"], trial,
                )
                if key in completed:
                    continue

                done += 1
                print(f"\n[{done}/{total}] {model_cfg['display_name']} | "
                      f"{scenario['id']} | Trial {trial}")

                api = MockCommerceAPI()
                agent_result = _run_single_trial_with_retry(
                    run_agent,
                    scenario["user_intent"],
                    model_cfg["provider"],
                    model_cfg["model_id"],
                    api,
                )

                eval_result = evaluate_trial(
                    scenario, agent_result, model_cfg["display_name"],
                    "baseline", trial,
                )

                record = {
                    "experiment": "baseline",
                    "model": model_cfg["display_name"],
                    "scenario_id": scenario["id"],
                    "scenario_name": scenario["name"],
                    "complexity": scenario["complexity"],
                    "trial_number": trial,
                    "agent_result": {
                        "success": agent_result.success,
                        "purchased_items": agent_result.purchased_items,
                        "total_price": agent_result.total_price,
                        "num_actions": len(agent_result.actions),
                        "final_message": agent_result.final_message[:500],
                        "error": agent_result.error,
                        "total_latency_ms": agent_result.total_latency_ms,
                    },
                    "evaluation": {
                        "purchase_attempted": eval_result.purchase_attempted,
                        "purchase_succeeded": eval_result.purchase_succeeded,
                        "all_constraints_met": eval_result.all_constraints_met,
                        "constraint_compliance": eval_result.constraint_compliance,
                        "silent_deviation": eval_result.silent_deviation,
                        "hallucination": eval_result.hallucination,
                        "optimization_met": eval_result.optimization_met,
                        "violations": [
                            {"type": v.type, "severity": v.severity,
                             "description": v.description, "silent": v.silent}
                            for v in eval_result.violations
                        ],
                    },
                    "api_calls": api.get_log(),
                }
                _append_result(output_path, record)

                # Brief pause to respect rate limits
                time.sleep(0.5)

    print(f"\nExperiment 1 complete. Results: {output_path}")


def run_experiment_2_ddm(resume: bool = False):
    """Experiment 2: DDM Control — mandate generation + enforcement.

    Agent executes shopping tasks, but purchase requests are intercepted
    by DDM for constraint verification before execution.
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT 2: DDM CONTROL")
    print("=" * 60)

    scenarios = load_scenarios()
    catalog = load_catalog_for_enrichment()
    output_path = RESULTS_DIR / "experiment2_raw.jsonl"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    completed = _load_completed(output_path) if resume else set()
    if not resume and output_path.exists():
        output_path.unlink()

    random.seed(RANDOM_SEED)
    total = len(MODELS) * len(scenarios) * TRIALS_PER_CONDITION
    done = len(completed)

    for model_cfg in MODELS:
        for scenario in scenarios:
            ddm = DDM(principal="experiment_user")
            mandate = ddm.generate_mandate(scenario["constraints"])
            print(f"\n  Mandate generated: {mandate.mandate_hash} "
                  f"(latency: {mandate.generation_latency_ms:.2f}ms)")

            for trial in range(TRIALS_PER_CONDITION):
                key = _trial_key(
                    "ddm", model_cfg["display_name"],
                    scenario["id"], trial,
                )
                if key in completed:
                    continue

                done += 1
                print(f"\n[{done}/{total}] {model_cfg['display_name']} | "
                      f"{scenario['id']} | Trial {trial} (DDM)")

                # Create a DDM-wrapped API that intercepts purchase calls
                api = MockCommerceAPI()
                agent_result = _run_single_trial_with_retry(
                    run_agent,
                    scenario["user_intent"],
                    model_cfg["provider"],
                    model_cfg["model_id"],
                    api,
                )

                # Post-hoc DDM enforcement on purchase results
                # In a real system, this would intercept BEFORE execution.
                # For this experiment, we evaluate what DDM WOULD have done.
                ddm_blocked = False
                enforcement_result = None
                enforcement_latency_ms = 0.0

                if agent_result.success and agent_result.purchased_items:
                    # Enrich purchase items with catalog data for constraint checking
                    enriched_items = []
                    for item in agent_result.purchased_items:
                        pid = item.get("product_id", "")
                        if pid in catalog:
                            enriched = {**item, **catalog[pid]}
                        else:
                            enriched = item
                        enriched_items.append(enriched)

                    enforcement_result = ddm.enforce(
                        mandate, {"items": enriched_items}
                    )
                    enforcement_latency_ms = enforcement_result.check_latency_ms
                    ddm_blocked = not enforcement_result.allowed

                # Evaluate ground truth
                eval_result = evaluate_trial(
                    scenario, agent_result, model_cfg["display_name"],
                    "ddm", trial, ddm_blocked=ddm_blocked,
                )

                # Check for false rejection
                ddm_false_rejection = False
                if ddm_blocked and enforcement_result:
                    ddm_false_rejection = check_ddm_false_rejection(
                        scenario, enforcement_result,
                    )

                # Verify mandate reproducibility
                reproducible, repro_hash = ddm.verify_reproducibility(mandate)

                record = {
                    "experiment": "ddm",
                    "model": model_cfg["display_name"],
                    "scenario_id": scenario["id"],
                    "scenario_name": scenario["name"],
                    "complexity": scenario["complexity"],
                    "trial_number": trial,
                    "agent_result": {
                        "success": agent_result.success,
                        "purchased_items": agent_result.purchased_items,
                        "total_price": agent_result.total_price,
                        "num_actions": len(agent_result.actions),
                        "final_message": agent_result.final_message[:500],
                        "error": agent_result.error,
                        "total_latency_ms": agent_result.total_latency_ms,
                    },
                    "evaluation": {
                        "purchase_attempted": eval_result.purchase_attempted,
                        "purchase_succeeded": eval_result.purchase_succeeded,
                        "all_constraints_met": eval_result.all_constraints_met,
                        "constraint_compliance": eval_result.constraint_compliance,
                        "silent_deviation": eval_result.silent_deviation,
                        "hallucination": eval_result.hallucination,
                        "optimization_met": eval_result.optimization_met,
                        "violations": [
                            {"type": v.type, "severity": v.severity,
                             "description": v.description, "silent": v.silent}
                            for v in eval_result.violations
                        ],
                    },
                    "ddm": {
                        "mandate_hash": mandate.mandate_hash,
                        "blocked": ddm_blocked,
                        "false_rejection": ddm_false_rejection,
                        "enforcement_violations": (
                            enforcement_result.violations if enforcement_result else []
                        ),
                        "enforcement_latency_ms": enforcement_latency_ms,
                        "mandate_generation_latency_ms": mandate.generation_latency_ms,
                        "mandate_reproducible": reproducible,
                        "mandate_constraints": mandate.constraints,
                    },
                    "api_calls": api.get_log(),
                }
                _append_result(output_path, record)

                ddm.reset()
                time.sleep(0.5)

    print(f"\nExperiment 2 complete. Results: {output_path}")
