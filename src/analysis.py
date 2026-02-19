"""Analysis module — computes summary statistics and generates paper outputs.

Reads raw JSONL experiment results and produces:
- summary_stats.json: all computed metrics
- tables_latex.tex: LaTeX tables for the paper
- analysis_report.md: human-readable report
"""

import json
import math
from collections import defaultdict
from pathlib import Path

from src.config import RESULTS_DIR


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


def _rate(count: int, total: int) -> float:
    return count / total if total > 0 else 0.0


def _ci95(rate: float, n: int) -> float:
    """95% confidence interval for a proportion (Wilson interval approximation)."""
    if n == 0:
        return 0.0
    return 1.96 * math.sqrt(rate * (1 - rate) / n)


def compute_baseline_stats(results: list[dict]) -> dict:
    """Compute Experiment 1 statistics."""
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

    # Compute rates
    summary = {}
    for model in stats:
        summary[model] = {}
        for scenario in stats[model]:
            s = stats[model][scenario]
            n = s["total"]
            ccr = _rate(s["compliant"], n)
            sdr = _rate(s["silent_dev"], n)
            hr = _rate(s["hallucination"], n)

            summary[model][scenario] = {
                "n": n,
                "CCR": round(ccr, 4),
                "CCR_ci95": round(_ci95(ccr, n), 4),
                "SDR": round(sdr, 4),
                "SDR_ci95": round(_ci95(sdr, n), 4),
                "HR": round(hr, 4),
                "HR_ci95": round(_ci95(hr, n), 4),
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
        summary[model]["ALL"] = {
            "n": all_total,
            "CCR": round(ccr, 4),
            "CCR_ci95": round(_ci95(ccr, all_total), 4),
            "SDR": round(sdr, 4),
            "SDR_ci95": round(_ci95(sdr, all_total), 4),
            "HR": round(hr, 4),
            "HR_ci95": round(_ci95(hr, all_total), 4),
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

        # After DDM: compliant means either agent was compliant OR DDM blocked violation
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
            vpr = _rate(s["blocked"], n)  # Violation Prevention Rate
            frr = _rate(s["false_reject"], max(s["blocked"], 1))

            lat_enf = s["enforcement_latencies"]
            lat_gen = s["mandate_gen_latencies"]

            summary[model][scenario] = {
                "n": n,
                "effective_CCR": round(ccr, 4),
                "effective_CCR_ci95": round(_ci95(ccr, n), 4),
                "VPR": round(vpr, 4),
                "FRR": round(frr, 4),
                "mean_enforcement_latency_ms": round(
                    sum(lat_enf) / len(lat_enf), 3) if lat_enf else 0,
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
        summary[model]["ALL"] = {
            "n": all_total,
            "effective_CCR": round(ccr, 4),
            "effective_CCR_ci95": round(_ci95(ccr, all_total), 4),
            "VPR": round(_rate(all_blocked, all_total), 4),
            "FRR": round(_rate(all_false, max(all_blocked, 1)), 4),
            "mean_enforcement_latency_ms": round(
                sum(all_enf_lat) / len(all_enf_lat), 3) if all_enf_lat else 0,
            "reproducibility_rate": round(_rate(all_repro, all_total), 4),
        }

    return summary


def generate_latex_tables(baseline: dict, ddm: dict) -> str:
    """Generate LaTeX tables for the paper."""
    lines = []

    # Table 1: Baseline results
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{Experiment 1: Baseline constraint compliance without DDM control. "
                 r"CCR = Constraint Compliance Rate, SDR = Silent Deviation Rate, "
                 r"HR = Hallucination Rate. 95\% confidence intervals shown.}")
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
            ccr = f"{s['CCR']:.1%} $\\pm$ {s['CCR_ci95']:.1%}"
            sdr = f"{s['SDR']:.1%} $\\pm$ {s['SDR_ci95']:.1%}"
            hr = f"{s['HR']:.1%} $\\pm$ {s['HR_ci95']:.1%}"
            lines.append(f"{model_col} & {scenario_label} & {ccr} & {sdr} & {hr} \\\\")
            first = False
        lines.append(r"\midrule")

    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    lines.append("")

    # Table 2: DDM results
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{Experiment 2: Effective constraint compliance with DDM control. "
                 r"VPR = Violation Prevention Rate (fraction of trials where DDM blocked a violation), "
                 r"FRR = False Rejection Rate, Latency = mean DDM enforcement overhead.}")
    lines.append(r"\label{tab:ddm}")
    lines.append(r"\small")
    lines.append(r"\begin{tabular}{llcccc}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Model} & \textbf{Scenario} & \textbf{Eff. CCR} & "
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
            eccr = f"{s['effective_CCR']:.1%} $\\pm$ {s.get('effective_CCR_ci95', 0):.1%}"
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

    # Table 3: Comparison
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


def generate_report(baseline: dict, ddm: dict) -> str:
    """Generate human-readable analysis report."""
    lines = ["# DDM Experiment Analysis Report\n"]

    lines.append("## Experiment 1: Baseline (No DDM)\n")
    for model in sorted(baseline.keys()):
        lines.append(f"### {model}\n")
        for scenario in ["S1", "S2", "S3", "ALL"]:
            if scenario not in baseline[model]:
                continue
            s = baseline[model][scenario]
            label = "Overall" if scenario == "ALL" else scenario
            lines.append(f"**{label}** (n={s['n']})")
            lines.append(f"- Constraint Compliance Rate: {s['CCR']:.1%} (±{s['CCR_ci95']:.1%})")
            lines.append(f"- Silent Deviation Rate: {s['SDR']:.1%}")
            lines.append(f"- Hallucination Rate: {s['HR']:.1%}")
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
            lines.append(f"**{label}** (n={s['n']})")
            lines.append(f"- Effective CCR: {s['effective_CCR']:.1%}")
            lines.append(f"- Violation Prevention Rate: {s['VPR']:.1%}")
            lines.append(f"- False Rejection Rate: {s['FRR']:.1%}")
            lines.append(f"- Mean enforcement latency: {s['mean_enforcement_latency_ms']:.1f}ms")
            lines.append(f"- Reproducibility: {s.get('reproducibility_rate', 0):.1%}")
            lines.append("")

    lines.append("## Comparison\n")
    lines.append("| Model | Baseline CCR | DDM Eff. CCR | Improvement |")
    lines.append("|---|---|---|---|")
    for model in sorted(set(list(baseline.keys()) + list(ddm.keys()))):
        b = baseline.get(model, {}).get("ALL", {}).get("CCR", 0)
        d = ddm.get(model, {}).get("ALL", {}).get("effective_CCR", 0)
        delta = d - b
        sign = "+" if delta >= 0 else ""
        lines.append(f"| {model} | {b:.1%} | {d:.1%} | {sign}{delta:.1%} |")

    return "\n".join(lines)


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

    baseline = compute_baseline_stats(exp1) if exp1 else {}
    ddm = compute_ddm_stats(exp2) if exp2 else {}

    # Save summary stats
    summary = {"baseline": baseline, "ddm": ddm}
    with open(RESULTS_DIR / "summary_stats.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Summary stats: {RESULTS_DIR / 'summary_stats.json'}")

    # Generate LaTeX tables
    latex = generate_latex_tables(baseline, ddm)
    with open(RESULTS_DIR / "tables_latex.tex", "w") as f:
        f.write(latex)
    print(f"LaTeX tables: {RESULTS_DIR / 'tables_latex.tex'}")

    # Generate report
    report = generate_report(baseline, ddm)
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
