"""Analysis module — computes summary statistics and generates paper outputs.

Reads raw JSONL experiment results and produces:
- summary_stats.json: all computed metrics with Wilson CI and inferential stats
- tables_latex.tex: LaTeX tables for the paper (4 tables)
- results_flat.csv: flat CSV with one row per trial
- analysis_report.md: human-readable report
"""

import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import RESULTS_DIR


# ============================================================
# Statistical Functions
# ============================================================

def _rate(count: int, total: int) -> float:
    return count / total if total > 0 else 0.0


def _wilson_ci(successes: int, total: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score confidence interval for binomial proportion.

    More accurate than normal approximation, especially for small n or
    proportions near 0 or 1.
    """
    if total == 0:
        return (0.0, 0.0)

    z = 1.96  # 95% CI
    p_hat = successes / total
    denom = 1 + z ** 2 / total
    center = (p_hat + z ** 2 / (2 * total)) / denom
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z ** 2 / (4 * total)) / total) / denom

    return (max(0.0, center - spread), min(1.0, center + spread))


def _cohens_h(p1: float, p2: float) -> float:
    """Cohen's h effect size for comparing two proportions.

    |h| < 0.2: small, 0.2-0.8: medium, > 0.8: large
    """
    return 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2))


def _mcnemar_exact_p(b: int, c: int) -> float:
    """McNemar's exact test p-value (two-sided).

    b = discordant pairs where baseline=1, ddm=0
    c = discordant pairs where baseline=0, ddm=1
    Uses exact binomial test.
    """
    if b + c == 0:
        return 1.0

    n = b + c
    k = min(b, c)

    # Binomial CDF: P(X <= k) where X ~ Binomial(n, 0.5)
    p = 0.0
    for i in range(k + 1):
        p += math.comb(n, i) * 0.5 ** n
    return min(1.0, 2 * p)  # two-sided


def _interpret_effect(h: float) -> str:
    v = abs(h)
    if v < 0.2:
        return "small"
    elif v < 0.8:
        return "medium"
    else:
        return "large"


def _format_pvalue_latex(p: float) -> str:
    if p < 0.001:
        return "$< 0.001$"
    return f"{p:.3f}"


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 0:
        return (s[n // 2 - 1] + s[n // 2]) / 2
    return s[n // 2]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


# ============================================================
# Data Loading
# ============================================================

def _load_results(filename: str) -> list[dict]:
    path = RESULTS_DIR / filename
    if not path.exists():
        return []
    results = []
    with open(path) as f:
        for line in f:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return results


# ============================================================
# Descriptive Statistics
# ============================================================

def compute_baseline_stats(results: list[dict]) -> dict:
    """Compute Experiment 1 statistics with Wilson CI."""
    stats = defaultdict(lambda: defaultdict(lambda: {
        "total": 0, "compliant": 0, "silent_dev": 0,
        "hallucination": 0, "optimization": 0, "no_purchase": 0,
        "violation_types": defaultdict(int),
    }))

    for r in results:
        model = r["model"]
        scenario = r["scenario_id"]
        e = r["evaluation"]
        s = stats[model][scenario]

        s["total"] += 1
        if e["constraint_compliance"]:
            s["compliant"] += 1
        if e["silent_deviation"]:
            s["silent_dev"] += 1
        if e["hallucination"]:
            s["hallucination"] += 1
        if e["optimization_met"]:
            s["optimization"] += 1
        if not e["purchase_succeeded"] and not e["purchase_attempted"]:
            s["no_purchase"] += 1

        for v in e["violations"]:
            s["violation_types"][v["type"]] += 1

    summary = {}
    for model in stats:
        summary[model] = {}
        for scenario in stats[model]:
            s = stats[model][scenario]
            n = s["total"]
            ccr = _rate(s["compliant"], n)
            sdr = _rate(s["silent_dev"], n)
            hr = _rate(s["hallucination"], n)
            ccr_lo, ccr_hi = _wilson_ci(s["compliant"], n)
            sdr_lo, sdr_hi = _wilson_ci(s["silent_dev"], n)
            hr_lo, hr_hi = _wilson_ci(s["hallucination"], n)

            summary[model][scenario] = {
                "n": n,
                "CCR": round(ccr, 4),
                "CCR_ci95": [round(ccr_lo, 4), round(ccr_hi, 4)],
                "SDR": round(sdr, 4),
                "SDR_ci95": [round(sdr_lo, 4), round(sdr_hi, 4)],
                "HR": round(hr, 4),
                "HR_ci95": [round(hr_lo, 4), round(hr_hi, 4)],
                "optimization_rate": round(_rate(s["optimization"], n), 4),
                "no_purchase_rate": round(_rate(s["no_purchase"], n), 4),
                "violation_breakdown": dict(s["violation_types"]),
            }

        # Aggregate across scenarios
        all_total = sum(stats[model][s]["total"] for s in stats[model])
        all_compliant = sum(stats[model][s]["compliant"] for s in stats[model])
        all_silent = sum(stats[model][s]["silent_dev"] for s in stats[model])
        all_halluc = sum(stats[model][s]["hallucination"] for s in stats[model])
        ccr = _rate(all_compliant, all_total)
        sdr = _rate(all_silent, all_total)
        hr = _rate(all_halluc, all_total)
        ccr_lo, ccr_hi = _wilson_ci(all_compliant, all_total)
        sdr_lo, sdr_hi = _wilson_ci(all_silent, all_total)
        hr_lo, hr_hi = _wilson_ci(all_halluc, all_total)
        summary[model]["ALL"] = {
            "n": all_total,
            "CCR": round(ccr, 4),
            "CCR_ci95": [round(ccr_lo, 4), round(ccr_hi, 4)],
            "SDR": round(sdr, 4),
            "SDR_ci95": [round(sdr_lo, 4), round(sdr_hi, 4)],
            "HR": round(hr, 4),
            "HR_ci95": [round(hr_lo, 4), round(hr_hi, 4)],
        }

    return summary


def compute_ddm_stats(results: list[dict]) -> dict:
    """Compute Experiment 2 statistics."""
    stats = defaultdict(lambda: defaultdict(lambda: {
        "total": 0, "compliant": 0, "blocked": 0, "false_reject": 0,
        "enforcement_latencies": [], "mandate_gen_latencies": [],
        "reproducible": 0,
        "violation_types_before_ddm": defaultdict(int),
    }))

    for r in results:
        model = r["model"]
        scenario = r["scenario_id"]
        s = stats[model][scenario]
        e = r["evaluation"]
        d = r.get("ddm", {})

        s["total"] += 1

        agent_compliant = e["constraint_compliance"]
        ddm_blocked_violation = d.get("blocked", False) and not d.get("false_rejection", False)
        if agent_compliant or ddm_blocked_violation:
            s["compliant"] += 1

        if d.get("blocked", False):
            s["blocked"] += 1
        if d.get("false_rejection", False):
            s["false_reject"] += 1
        if d.get("mandate_reproducible", False):
            s["reproducible"] += 1

        if d.get("enforcement_latency_ms"):
            s["enforcement_latencies"].append(d["enforcement_latency_ms"])
        if d.get("mandate_generation_latency_ms"):
            s["mandate_gen_latencies"].append(d["mandate_generation_latency_ms"])

        for v in e["violations"]:
            s["violation_types_before_ddm"][v["type"]] += 1

    summary = {}
    for model in stats:
        summary[model] = {}
        for scenario in stats[model]:
            s = stats[model][scenario]
            n = s["total"]
            ccr = _rate(s["compliant"], n)
            vpr = _rate(s["blocked"], n)
            frr = _rate(s["false_reject"], max(s["blocked"], 1))
            ccr_lo, ccr_hi = _wilson_ci(s["compliant"], n)

            lat_enf = s["enforcement_latencies"]
            lat_gen = s["mandate_gen_latencies"]

            summary[model][scenario] = {
                "n": n,
                "effective_CCR": round(ccr, 4),
                "effective_CCR_ci95": [round(ccr_lo, 4), round(ccr_hi, 4)],
                "VPR": round(vpr, 4),
                "FRR": round(frr, 4),
                "mean_enforcement_latency_ms": round(
                    sum(lat_enf) / len(lat_enf), 3) if lat_enf else 0,
                "median_enforcement_latency_ms": round(
                    _median(lat_enf), 3) if lat_enf else 0,
                "mean_mandate_gen_latency_ms": round(
                    sum(lat_gen) / len(lat_gen), 3) if lat_gen else 0,
                "reproducibility_rate": round(_rate(s["reproducible"], n), 4),
                "violation_breakdown_before_ddm": dict(s["violation_types_before_ddm"]),
            }

        # Aggregate
        all_total = sum(stats[model][s]["total"] for s in stats[model])
        all_compliant = sum(stats[model][s]["compliant"] for s in stats[model])
        all_blocked = sum(stats[model][s]["blocked"] for s in stats[model])
        all_false = sum(stats[model][s]["false_reject"] for s in stats[model])
        all_repro = sum(stats[model][s]["reproducible"] for s in stats[model])
        all_enf_lat = [
            l for s in stats[model] for l in stats[model][s]["enforcement_latencies"]
        ]
        ccr = _rate(all_compliant, all_total)
        ccr_lo, ccr_hi = _wilson_ci(all_compliant, all_total)
        summary[model]["ALL"] = {
            "n": all_total,
            "effective_CCR": round(ccr, 4),
            "effective_CCR_ci95": [round(ccr_lo, 4), round(ccr_hi, 4)],
            "VPR": round(_rate(all_blocked, all_total), 4),
            "FRR": round(_rate(all_false, max(all_blocked, 1)), 4),
            "mean_enforcement_latency_ms": round(
                sum(all_enf_lat) / len(all_enf_lat), 3) if all_enf_lat else 0,
            "median_enforcement_latency_ms": round(
                _median(all_enf_lat), 3) if all_enf_lat else 0,
            "reproducibility_rate": round(_rate(all_repro, all_total), 4),
        }

    return summary


# ============================================================
# Inferential Statistics
# ============================================================

def compute_inferential_stats(
    exp1: list[dict], exp2: list[dict]
) -> dict:
    """Compute McNemar test + Cohen's h for Baseline vs DDM comparison.

    Pairs trials by (model, scenario_id, trial_number).
    """
    # Index exp1 and exp2 by (model, scenario, trial)
    def _key(r):
        return (r["model"], r["scenario_id"], r["trial_number"])

    exp1_map = {_key(r): r for r in exp1 if not r["agent_result"].get("error")}
    exp2_map = {_key(r): r for r in exp2 if not r["agent_result"].get("error")}

    # Find common keys
    common = sorted(set(exp1_map.keys()) & set(exp2_map.keys()))
    if not common:
        return {}

    results = {}
    for metric_name, metric_fn in [
        ("CCR", lambda e: 1 if e["constraint_compliance"] else 0),
        ("SDR", lambda e: 1 if e["silent_deviation"] else 0),
        ("HR", lambda e: 1 if e["hallucination"] else 0),
    ]:
        b_vals = []
        d_vals = []
        for k in common:
            b_eval = exp1_map[k]["evaluation"]
            d_eval = exp2_map[k]["evaluation"]
            # For DDM effective CCR: count DDM-blocked violations as compliant
            if metric_name == "CCR":
                d_ddm = exp2_map[k].get("ddm", {})
                ddm_blocked_violation = d_ddm.get("blocked", False) and not d_ddm.get("false_rejection", False)
                d_val = 1 if (d_eval["constraint_compliance"] or ddm_blocked_violation) else 0
            else:
                d_val = metric_fn(d_eval)
                # If DDM blocked, SDR and HR are 0
                d_ddm = exp2_map[k].get("ddm", {})
                if d_ddm.get("blocked", False) and not d_ddm.get("false_rejection", False):
                    d_val = 0
            b_vals.append(metric_fn(b_eval))
            d_vals.append(d_val)

        n = len(b_vals)
        p_b = sum(b_vals) / n if n else 0
        p_d = sum(d_vals) / n if n else 0

        # McNemar contingency
        b_count = sum(1 for bv, dv in zip(b_vals, d_vals) if bv == 1 and dv == 0)
        c_count = sum(1 for bv, dv in zip(b_vals, d_vals) if bv == 0 and dv == 1)

        p_value = _mcnemar_exact_p(b_count, c_count)
        h = _cohens_h(p_d, p_b)

        results[metric_name] = {
            "n_paired": n,
            "baseline_rate": round(p_b, 4),
            "ddm_rate": round(p_d, 4),
            "delta": round(p_d - p_b, 4),
            "mcnemar_discordant_b": b_count,
            "mcnemar_discordant_c": c_count,
            "mcnemar_p_value": round(p_value, 6),
            "cohens_h": round(h, 4),
            "effect_interpretation": _interpret_effect(h),
            "significant_005": p_value < 0.05,
        }

    # Per-model breakdown
    models = sorted(set(k[0] for k in common))
    results["by_model"] = {}
    for model in models:
        model_keys = [k for k in common if k[0] == model]
        model_results = {}
        for metric_name, metric_fn in [
            ("CCR", lambda e: 1 if e["constraint_compliance"] else 0),
        ]:
            b_vals = [metric_fn(exp1_map[k]["evaluation"]) for k in model_keys]
            d_vals = []
            for k in model_keys:
                d_eval = exp2_map[k]["evaluation"]
                d_ddm = exp2_map[k].get("ddm", {})
                ddm_ok = d_ddm.get("blocked", False) and not d_ddm.get("false_rejection", False)
                d_vals.append(1 if (d_eval["constraint_compliance"] or ddm_ok) else 0)

            p_b = sum(b_vals) / len(b_vals) if b_vals else 0
            p_d = sum(d_vals) / len(d_vals) if d_vals else 0
            b_count = sum(1 for bv, dv in zip(b_vals, d_vals) if bv == 1 and dv == 0)
            c_count = sum(1 for bv, dv in zip(b_vals, d_vals) if bv == 0 and dv == 1)

            model_results[metric_name] = {
                "n_paired": len(b_vals),
                "baseline_rate": round(p_b, 4),
                "ddm_rate": round(p_d, 4),
                "delta": round(p_d - p_b, 4),
                "mcnemar_p_value": round(_mcnemar_exact_p(b_count, c_count), 6),
                "cohens_h": round(_cohens_h(p_d, p_b), 4),
            }
        results["by_model"][model] = model_results

    return results


def compute_scenario_comparison(
    exp1: list[dict], exp2: list[dict]
) -> dict:
    """Compute per-scenario Baseline vs DDM comparison."""
    def _key(r):
        return (r["model"], r["scenario_id"], r["trial_number"])

    exp1_map = {_key(r): r for r in exp1 if not r["agent_result"].get("error")}
    exp2_map = {_key(r): r for r in exp2 if not r["agent_result"].get("error")}
    common = sorted(set(exp1_map.keys()) & set(exp2_map.keys()))

    scenarios = sorted(set(k[1] for k in common))
    result = {}

    for sid in scenarios:
        sid_keys = [k for k in common if k[1] == sid]
        scenario_metrics = {}
        for metric_name, metric_fn in [
            ("CCR", lambda e: 1 if e["constraint_compliance"] else 0),
            ("SDR", lambda e: 1 if e["silent_deviation"] else 0),
            ("HR", lambda e: 1 if e["hallucination"] else 0),
        ]:
            b_vals = [metric_fn(exp1_map[k]["evaluation"]) for k in sid_keys]
            d_vals = []
            for k in sid_keys:
                d_eval = exp2_map[k]["evaluation"]
                d_ddm = exp2_map[k].get("ddm", {})
                if metric_name == "CCR":
                    ddm_ok = d_ddm.get("blocked", False) and not d_ddm.get("false_rejection", False)
                    d_vals.append(1 if (d_eval["constraint_compliance"] or ddm_ok) else 0)
                else:
                    dv = metric_fn(d_eval)
                    if d_ddm.get("blocked", False) and not d_ddm.get("false_rejection", False):
                        dv = 0
                    d_vals.append(dv)

            p_b = sum(b_vals) / len(b_vals) if b_vals else 0
            p_d = sum(d_vals) / len(d_vals) if d_vals else 0
            scenario_metrics[metric_name] = {
                "baseline": round(p_b, 4),
                "ddm": round(p_d, 4),
                "delta": round(p_d - p_b, 4),
                "n": len(b_vals),
            }
        result[sid] = scenario_metrics

    return result


# ============================================================
# CSV Output
# ============================================================

def generate_csv(exp1: list[dict], exp2: list[dict], output_path: Path):
    """Generate flat CSV with one row per trial."""
    fieldnames = [
        "experiment", "model", "scenario_id", "complexity", "trial_number",
        "agent_success", "purchase_succeeded", "total_price", "num_actions",
        "constraint_compliance", "silent_deviation", "hallucination",
        "optimization_met", "violation_types",
        "ddm_blocked", "ddm_false_rejection",
        "ddm_enforcement_latency_ms", "ddm_mandate_reproducible",
        "agent_latency_ms", "error",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for records, exp_name in [(exp1, "baseline"), (exp2, "ddm")]:
            for r in sorted(records, key=lambda x: (x["model"], x["scenario_id"], x["trial_number"])):
                e = r["evaluation"]
                d = r.get("ddm", {})
                vtypes = "|".join(v["type"] for v in e["violations"]) if e["violations"] else ""
                row = {
                    "experiment": exp_name,
                    "model": r["model"],
                    "scenario_id": r["scenario_id"],
                    "complexity": r.get("complexity", ""),
                    "trial_number": r["trial_number"],
                    "agent_success": int(r["agent_result"]["success"]),
                    "purchase_succeeded": int(e["purchase_succeeded"]),
                    "total_price": r["agent_result"]["total_price"],
                    "num_actions": r["agent_result"]["num_actions"],
                    "constraint_compliance": int(e["constraint_compliance"]),
                    "silent_deviation": int(e["silent_deviation"]),
                    "hallucination": int(e["hallucination"]),
                    "optimization_met": int(e["optimization_met"]),
                    "violation_types": vtypes,
                    "ddm_blocked": int(d.get("blocked", False)) if d else "",
                    "ddm_false_rejection": int(d.get("false_rejection", False)) if d else "",
                    "ddm_enforcement_latency_ms": d.get("enforcement_latency_ms", "") if d else "",
                    "ddm_mandate_reproducible": int(d.get("mandate_reproducible", False)) if d else "",
                    "agent_latency_ms": r["agent_result"].get("total_latency_ms", ""),
                    "error": r["agent_result"].get("error", "")[:200] if r["agent_result"].get("error") else "",
                }
                writer.writerow(row)

    print(f"CSV: {output_path}")


# ============================================================
# LaTeX Output
# ============================================================

def generate_latex_tables(
    baseline: dict, ddm: dict,
    inferential: dict, scenario_comp: dict,
) -> str:
    """Generate LaTeX tables for the paper (4 tables)."""
    lines = []
    lines.append(f"% Auto-generated by ddm-eval-pipeline at {datetime.utcnow().isoformat()}Z")
    lines.append("")

    # ----------------------------------------------------------
    # Table 1: Baseline results
    # ----------------------------------------------------------
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{Experiment 1: Baseline constraint compliance without DDM control. "
                 r"CCR = Constraint Compliance Rate, SDR = Silent Deviation Rate, "
                 r"HR = Hallucination Rate. Wilson 95\% confidence intervals shown.}")
    lines.append(r"\label{tab:baseline}")
    lines.append(r"\small")
    lines.append(r"\begin{tabular}{llccc}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Model} & \textbf{Scenario} & \textbf{CCR} & \textbf{SDR} & \textbf{HR} \\")
    lines.append(r"\midrule")

    for model in sorted(baseline.keys()):
        first = True
        for scenario in ["S1", "S2", "S3", "ALL"]:
            if scenario not in baseline[model]:
                continue
            s = baseline[model][scenario]
            model_col = model if first else ""
            if scenario == "ALL":
                lines.append(r"\cmidrule{2-5}")
                scenario_label = r"\textit{Overall}"
            else:
                scenario_label = scenario
            ccr = _fmt_ci(s["CCR"], s["CCR_ci95"])
            sdr = _fmt_ci(s["SDR"], s["SDR_ci95"])
            hr = _fmt_ci(s["HR"], s["HR_ci95"])
            lines.append(f"{model_col} & {scenario_label} & {ccr} & {sdr} & {hr} \\\\")
            first = False
        lines.append(r"\midrule")

    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    lines.append("")

    # ----------------------------------------------------------
    # Table 2: DDM results
    # ----------------------------------------------------------
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{Experiment 2: Effective constraint compliance with DDM control. "
                 r"VPR = Violation Prevention Rate, "
                 r"FRR = False Rejection Rate, Latency = mean DDM enforcement overhead.}")
    lines.append(r"\label{tab:ddm}")
    lines.append(r"\small")
    lines.append(r"\begin{tabular}{llcccc}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Model} & \textbf{Scenario} & \textbf{Eff.\ CCR} & "
                 r"\textbf{VPR} & \textbf{FRR} & \textbf{Latency} \\")
    lines.append(r"\midrule")

    for model in sorted(ddm.keys()):
        first = True
        for scenario in ["S1", "S2", "S3", "ALL"]:
            if scenario not in ddm[model]:
                continue
            s = ddm[model][scenario]
            model_col = model if first else ""
            if scenario == "ALL":
                lines.append(r"\cmidrule{2-6}")
                scenario_label = r"\textit{Overall}"
            else:
                scenario_label = scenario
            eccr = _fmt_ci(s["effective_CCR"], s.get("effective_CCR_ci95", [0, 0]))
            vpr = f"{s['VPR']:.1%}"
            frr = f"{s['FRR']:.1%}"
            lat = f"{s['mean_enforcement_latency_ms']:.1f}ms"
            lines.append(f"{model_col} & {scenario_label} & {eccr} & {vpr} & {frr} & {lat} \\\\")
            first = False
        lines.append(r"\midrule")

    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    lines.append("")

    # ----------------------------------------------------------
    # Table 3: Statistical significance summary
    # ----------------------------------------------------------
    if inferential:
        lines.append(r"\begin{table}[t]")
        lines.append(r"\centering")
        lines.append(r"\caption{Statistical Analysis: Baseline vs.\ DDM-Controlled Execution. "
                     r"McNemar's exact test with Cohen's $h$ effect size.}")
        lines.append(r"\label{tab:stats}")
        lines.append(r"\small")
        lines.append(r"\begin{tabular}{lccccc}")
        lines.append(r"\toprule")
        lines.append(r"\textbf{Metric} & \textbf{Baseline} & \textbf{DDM} & "
                     r"\textbf{$p$-value} & \textbf{Cohen's $h$} & \textbf{Sig.} \\")
        lines.append(r"\midrule")

        for metric in ["CCR", "SDR", "HR"]:
            if metric in inferential:
                inf = inferential[metric]
                bl = f"{inf['baseline_rate']:.2f}"
                ddm_val = f"{inf['ddm_rate']:.2f}"
                p_val = _format_pvalue_latex(inf["mcnemar_p_value"])
                h_val = f"{inf['cohens_h']:.2f}"
                sig = r"\checkmark" if inf["significant_005"] else "---"
                lines.append(f"{metric} & {bl} & {ddm_val} & {p_val} & {h_val} & {sig} \\\\")

        lines.append(r"\bottomrule")
        lines.append(r"\end{tabular}")
        lines.append(r"\end{table}")
        lines.append("")

    # ----------------------------------------------------------
    # Table 4: Scenario-wise breakdown (Baseline vs DDM)
    # ----------------------------------------------------------
    if scenario_comp:
        lines.append(r"\begin{table*}[t]")
        lines.append(r"\centering")
        lines.append(r"\caption{Constraint Compliance Rate by Scenario Complexity and Condition}")
        lines.append(r"\label{tab:breakdown}")
        lines.append(r"\small")
        lines.append(r"\begin{tabular}{llccc}")
        lines.append(r"\toprule")
        lines.append(r"\textbf{Scenario} & \textbf{Condition} & \textbf{CCR} & \textbf{SDR} & \textbf{HR} \\")
        lines.append(r"\midrule")

        complexity_labels = {"S1": "Low", "S2": "Medium", "S3": "High"}
        for sid in ["S1", "S2", "S3"]:
            if sid not in scenario_comp:
                continue
            sc = scenario_comp[sid]
            clabel = complexity_labels.get(sid, sid)
            bl_ccr = f"{sc['CCR']['baseline']:.2f}"
            bl_sdr = f"{sc['SDR']['baseline']:.2f}"
            bl_hr = f"{sc['HR']['baseline']:.2f}"
            ddm_ccr = f"{sc['CCR']['ddm']:.2f}"
            ddm_sdr = f"{sc['SDR']['ddm']:.2f}"
            ddm_hr = f"{sc['HR']['ddm']:.2f}"

            lines.append(f"\\multirow{{2}}{{*}}{{{sid} ({clabel})}}")
            lines.append(f"  & Baseline & {bl_ccr} & {bl_sdr} & {bl_hr} \\\\")
            lines.append(f"  & DDM      & {ddm_ccr} & {ddm_sdr} & {ddm_hr} \\\\")
            lines.append(r"\midrule")

        if lines[-1] == r"\midrule":
            lines[-1] = r"\bottomrule"
        lines.append(r"\end{tabular}")
        lines.append(r"\end{table*}")

    # ----------------------------------------------------------
    # Table 5: Comparison (simple)
    # ----------------------------------------------------------
    lines.append("")
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{Comparison: Baseline vs.\ DDM overall constraint compliance.}")
    lines.append(r"\label{tab:comparison}")
    lines.append(r"\small")
    lines.append(r"\begin{tabular}{lccc}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Model} & \textbf{Baseline CCR} & \textbf{DDM Eff.\ CCR} & "
                 r"\textbf{Improvement} \\")
    lines.append(r"\midrule")

    for model in sorted(set(list(baseline.keys()) + list(ddm.keys()))):
        b_ccr = baseline.get(model, {}).get("ALL", {}).get("CCR", 0)
        d_ccr = ddm.get(model, {}).get("ALL", {}).get("effective_CCR", 0)
        delta = d_ccr - b_ccr
        sign = "+" if delta >= 0 else ""
        lines.append(f"{model} & {b_ccr:.1%} & {d_ccr:.1%} & {sign}{delta:.1%} \\\\")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")

    return "\n".join(lines)


def _fmt_ci(rate: float, ci: list[float]) -> str:
    """Format rate with Wilson CI for LaTeX."""
    if isinstance(ci, list) and len(ci) == 2:
        return f"{rate:.2f} [{ci[0]:.2f}, {ci[1]:.2f}]"
    return f"{rate:.2f}"


# ============================================================
# Markdown Report
# ============================================================

def generate_report(
    baseline: dict, ddm: dict,
    inferential: dict, scenario_comp: dict,
) -> str:
    """Generate human-readable analysis report."""
    lines = ["# DDM Experiment Analysis Report\n"]
    lines.append(f"Generated: {datetime.utcnow().isoformat()}Z\n")

    lines.append("## Experiment 1: Baseline (No DDM)\n")
    for model in sorted(baseline.keys()):
        lines.append(f"### {model}\n")
        for scenario in ["S1", "S2", "S3", "ALL"]:
            if scenario not in baseline[model]:
                continue
            s = baseline[model][scenario]
            label = "Overall" if scenario == "ALL" else scenario
            ci_ccr = s["CCR_ci95"]
            ci_sdr = s["SDR_ci95"]
            ci_hr = s["HR_ci95"]
            lines.append(f"**{label}** (n={s['n']})")
            lines.append(f"- CCR: {s['CCR']:.1%} [{ci_ccr[0]:.1%}, {ci_ccr[1]:.1%}]")
            lines.append(f"- SDR: {s['SDR']:.1%} [{ci_sdr[0]:.1%}, {ci_sdr[1]:.1%}]")
            lines.append(f"- HR:  {s['HR']:.1%} [{ci_hr[0]:.1%}, {ci_hr[1]:.1%}]")
            if "violation_breakdown" in s:
                lines.append(f"- Violations: {s['violation_breakdown']}")
            lines.append("")

    lines.append("## Experiment 2: DDM Control\n")
    for model in sorted(ddm.keys()):
        lines.append(f"### {model}\n")
        for scenario in ["S1", "S2", "S3", "ALL"]:
            if scenario not in ddm[model]:
                continue
            s = ddm[model][scenario]
            label = "Overall" if scenario == "ALL" else scenario
            ci = s.get("effective_CCR_ci95", [0, 0])
            lines.append(f"**{label}** (n={s['n']})")
            lines.append(f"- Effective CCR: {s['effective_CCR']:.1%} [{ci[0]:.1%}, {ci[1]:.1%}]")
            lines.append(f"- VPR: {s['VPR']:.1%}")
            lines.append(f"- FRR: {s['FRR']:.1%}")
            lines.append(f"- Mean enforcement latency: {s['mean_enforcement_latency_ms']:.1f}ms")
            lines.append(f"- Reproducibility: {s.get('reproducibility_rate', 0):.1%}")
            lines.append("")

    # Inferential statistics
    if inferential:
        lines.append("## Statistical Analysis (Baseline vs DDM)\n")
        lines.append("| Metric | Baseline | DDM | Delta | p-value | Cohen's h | Effect | Sig. |")
        lines.append("|--------|----------|-----|-------|---------|-----------|--------|------|")
        for metric in ["CCR", "SDR", "HR"]:
            if metric in inferential:
                inf = inferential[metric]
                sig = "Yes" if inf["significant_005"] else "No"
                p_str = "< 0.001" if inf["mcnemar_p_value"] < 0.001 else f"{inf['mcnemar_p_value']:.3f}"
                lines.append(
                    f"| {metric} | {inf['baseline_rate']:.2f} | {inf['ddm_rate']:.2f} | "
                    f"{inf['delta']:+.2f} | {p_str} | {inf['cohens_h']:.2f} | "
                    f"{inf['effect_interpretation']} | {sig} |"
                )
        lines.append("")

    # Scenario comparison
    if scenario_comp:
        lines.append("## Scenario-wise Comparison\n")
        lines.append("| Scenario | Metric | Baseline | DDM | Delta |")
        lines.append("|----------|--------|----------|-----|-------|")
        for sid in ["S1", "S2", "S3"]:
            if sid not in scenario_comp:
                continue
            for metric in ["CCR", "SDR", "HR"]:
                sc = scenario_comp[sid][metric]
                lines.append(
                    f"| {sid} | {metric} | {sc['baseline']:.2f} | {sc['ddm']:.2f} | "
                    f"{sc['delta']:+.2f} |"
                )
        lines.append("")

    # Model comparison
    lines.append("## Model Comparison\n")
    lines.append("| Model | Baseline CCR | DDM Eff. CCR | Improvement |")
    lines.append("|---|---|---|---|")
    for model in sorted(set(list(baseline.keys()) + list(ddm.keys()))):
        b = baseline.get(model, {}).get("ALL", {}).get("CCR", 0)
        d = ddm.get(model, {}).get("ALL", {}).get("effective_CCR", 0)
        delta = d - b
        sign = "+" if delta >= 0 else ""
        lines.append(f"| {model} | {b:.1%} | {d:.1%} | {sign}{delta:.1%} |")

    return "\n".join(lines)


# ============================================================
# Main Entry Point
# ============================================================

def run_analysis():
    """Main analysis entry point."""
    print("\n" + "=" * 60)
    print("ANALYSIS")
    print("=" * 60)

    exp1 = _load_results("experiment1_raw.jsonl")
    exp2 = _load_results("experiment2_raw.jsonl")

    if not exp1 and not exp2:
        print("No results found. Run experiments first.")
        return

    # Filter out error trials for statistics
    exp1_valid = [r for r in exp1 if not r["agent_result"].get("error")]
    exp2_valid = [r for r in exp2 if not r["agent_result"].get("error")]

    print(f"Exp1: {len(exp1_valid)} valid / {len(exp1)} total trials")
    print(f"Exp2: {len(exp2_valid)} valid / {len(exp2)} total trials")

    baseline = compute_baseline_stats(exp1_valid) if exp1_valid else {}
    ddm = compute_ddm_stats(exp2_valid) if exp2_valid else {}

    # Inferential statistics
    inferential = {}
    scenario_comp = {}
    if exp1_valid and exp2_valid:
        print("Computing inferential statistics...")
        inferential = compute_inferential_stats(exp1_valid, exp2_valid)
        scenario_comp = compute_scenario_comparison(exp1_valid, exp2_valid)

    # Save summary stats
    summary = {
        "baseline": baseline,
        "ddm": ddm,
        "inferential": inferential,
        "scenario_comparison": scenario_comp,
    }
    with open(RESULTS_DIR / "summary_stats.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Summary stats: {RESULTS_DIR / 'summary_stats.json'}")

    # Generate LaTeX tables
    latex = generate_latex_tables(baseline, ddm, inferential, scenario_comp)
    with open(RESULTS_DIR / "tables_latex.tex", "w") as f:
        f.write(latex)
    print(f"LaTeX tables: {RESULTS_DIR / 'tables_latex.tex'}")

    # Generate CSV
    generate_csv(exp1, exp2, RESULTS_DIR / "results_flat.csv")

    # Generate report
    report = generate_report(baseline, ddm, inferential, scenario_comp)
    with open(RESULTS_DIR / "analysis_report.md", "w") as f:
        f.write(report)
    print(f"Report: {RESULTS_DIR / 'analysis_report.md'}")

    # Print key findings
    print("\n--- KEY FINDINGS ---")
    for model in sorted(set(list(baseline.keys()) + list(ddm.keys()))):
        b_ccr = baseline.get(model, {}).get("ALL", {}).get("CCR", 0)
        d_ccr = ddm.get(model, {}).get("ALL", {}).get("effective_CCR", 0)
        print(f"{model}: Baseline CCR={b_ccr:.1%} → DDM CCR={d_ccr:.1%} "
              f"(Δ={d_ccr - b_ccr:+.1%})")

    if inferential:
        print("\n--- STATISTICAL SIGNIFICANCE ---")
        for metric in ["CCR", "SDR", "HR"]:
            if metric in inferential:
                inf = inferential[metric]
                sig = "***" if inf["significant_005"] else "n.s."
                p_str = "< 0.001" if inf["mcnemar_p_value"] < 0.001 else f"{inf['mcnemar_p_value']:.4f}"
                print(f"  {metric}: Δ={inf['delta']:+.4f}, p={p_str}, "
                      f"h={inf['cohens_h']:.3f} ({inf['effect_interpretation']}) {sig}")
