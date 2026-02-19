"""Configuration constants for DDM experiments."""

import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_DIR = PROJECT_ROOT / "results"
CATALOG_PATH = DATA_DIR / "catalog.json"
SCENARIOS_PATH = DATA_DIR / "scenarios.json"

# Experiment parameters
TRIALS_PER_CONDITION = 30
RANDOM_SEED = 42
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds

# Models to test
MODELS = []

if os.environ.get("OPENAI_API_KEY"):
    MODELS.append({
        "provider": "openai",
        "model_id": "gpt-4o",
        "display_name": "GPT-4o",
    })

if os.environ.get("ANTHROPIC_API_KEY"):
    MODELS.append({
        "provider": "anthropic",
        "model_id": "claude-sonnet-4-20250514",
        "display_name": "Claude Sonnet 4",
    })

# Warning printed at import time; run_all.py will check before running experiments
if not MODELS:
    import warnings
    warnings.warn(
        "No API keys found. Set OPENAI_API_KEY and/or ANTHROPIC_API_KEY "
        "before running experiments. Dry-run tests will still work."
    )

# Agent settings
AGENT_MAX_TURNS = 10  # max tool-use turns per trial
AGENT_TEMPERATURE = 0.0  # deterministic as possible
