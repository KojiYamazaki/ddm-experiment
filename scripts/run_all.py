#!/usr/bin/env python3
"""DDM Experiment — Main Entry Point.

Usage:
    python scripts/run_all.py              # Run everything from scratch
    python scripts/run_all.py --resume     # Resume from where it stopped
    python scripts/run_all.py --exp1-only  # Run only Experiment 1
    python scripts/run_all.py --exp2-only  # Run only Experiment 2
    python scripts/run_all.py --analyze    # Run only analysis on existing data
"""

import argparse
import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import MODELS, TRIALS_PER_CONDITION, RESULTS_DIR

def main():
    parser = argparse.ArgumentParser(description="DDM Experiment Runner")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from previous run")
    parser.add_argument("--exp1-only", action="store_true",
                        help="Run only Experiment 1 (baseline)")
    parser.add_argument("--exp2-only", action="store_true",
                        help="Run only Experiment 2 (DDM)")
    parser.add_argument("--analyze", action="store_true",
                        help="Run only analysis on existing results")
    args = parser.parse_args()

    if not args.analyze and not MODELS:
        print("ERROR: No API keys found.")
        print("Set OPENAI_API_KEY and/or ANTHROPIC_API_KEY environment variables.")
        sys.exit(1)

    print("=" * 60)
    print("DDM EXPERIMENT RUNNER")
    print("Deterministic Delegation Model for Autonomous Agent Execution")
    print("=" * 60)
    print(f"\nModels configured: {[m['display_name'] for m in MODELS]}")
    print(f"Trials per condition: {TRIALS_PER_CONDITION}")
    print(f"Results directory: {RESULTS_DIR}")

    total_api_calls = len(MODELS) * 3 * TRIALS_PER_CONDITION  # per experiment
    run_exp1 = not args.exp2_only and not args.analyze
    run_exp2 = not args.exp1_only and not args.analyze

    if run_exp1 or run_exp2:
        estimated = total_api_calls * (1 if args.exp1_only or args.exp2_only else 2)
        print(f"\nEstimated API calls: ~{estimated}")
        print(f"Estimated time: ~{estimated * 5 / 60:.0f}–{estimated * 15 / 60:.0f} minutes")
        print(f"(Depends on API latency and rate limits)\n")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    start_time = time.time()

    # Import experiment modules
    from src.experiment import run_experiment_1_baseline, run_experiment_2_ddm
    from src.analysis import run_analysis

    if run_exp1:
        run_experiment_1_baseline(resume=args.resume)

    if run_exp2:
        run_experiment_2_ddm(resume=args.resume)

    # Always run analysis at the end
    run_analysis()

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"ALL DONE. Total time: {elapsed / 60:.1f} minutes")
    print(f"Results in: {RESULTS_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
