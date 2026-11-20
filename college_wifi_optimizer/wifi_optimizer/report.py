"""Result tables and the written project report, built from a PlanResult.

Pure pandas / NetworkX code with no Streamlit dependency, so the dashboard and tests can share it.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

import networkx as nx
import pandas as pd

from .planner import ALGORITHM_LABELS, PlanResult
from .solution import MODE_LABELS, Solution


def campus_signature(campus) -> str:
    """Stable fingerprint of a campus layout, used to detect edits made after an optimization run."""
    payload = json.dumps(campus.normalised().to_dict(), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _label(plan: PlanResult, sol: Solution) -> str:
    for key, s in plan.solutions.items():
        if s is sol:
            return ALGORITHM_LABELS[key]
    return sol.algorithm


def solution_table(plan: PlanResult) -> pd.DataFrame:
    """One row per configuration: the initial network and every algorithm that was run."""
    rows = []
    entries = [("Initial (existing)", plan.initial)] + [
        (ALGORITHM_LABELS[k], s) for k, s in plan.solutions.items()]
    for label, sol in entries:
        rows.append({
            "Configuration": label, "APs in config": len(sol.selected),
            "New APs": len(sol.new_aps), "Coverage": f"{sol.coverage_pct:.1%}",
            "Uncovered": len(sol.uncovered), "AP cost": round(sol.ap_cost, 2),
            "Runtime (ms)": round(sol.runtime_s * 1000, 2),
            "Target met": "yes" if sol.feasible else "no", "Note": sol.note,
        })
    return pd.DataFrame(rows)


def ap_table(plan: PlanResult, sol: Solution | None = None) -> pd.DataFrame:
    """Every AP in a configuration: where it is, what it costs and how much it serves."""
    sol = sol or plan.best
    g, model = plan.graph, plan.model
    existing = set(model.existing)
    run = nx.single_source_dijkstra_path_length(g, plan.campus.server_id, weight="distance")
    rows = []
    for ap in sol.selected:
        node = g.nodes[ap]
        served = model.sets[ap]
        is_new = ap not in existing
        rows.append({
            "AP": ap, "Name": node["name"], "Building": node["building"], "Floor": int(node["floor"]),
            "Status": "New" if is_new else "Existing",
            "Install cost": round(model.cost[ap], 2) if is_new else 0.0,
            "Locations served": len(served),
            "Devices served": int(sum(g.nodes[t]["devices"] for t in served)),
            "Cable run from server (m)": round(run.get(ap, float("nan")), 1) if is_new else 0.0,
        })
    return pd.DataFrame(rows, columns=["AP", "Name", "Building", "Floor", "Status", "Install cost",
                                       "Locations served", "Devices served",
                                       "Cable run from server (m)"])


def uncovered_table(plan: PlanResult, sol: Solution | None = None) -> pd.DataFrame:
    """Locations that still lack Wi-Fi, with the best signal they get and the likely reason."""
    sol = sol or plan.best
    g, model = plan.graph, plan.model
    thr = plan.net.signal.min_signal_dbm
    tidx = {t: i for i, t in enumerate(model.targets)}
    chosen = set(sol.selected)
    sel_rows = [i for i, c in enumerate(model.candidates) if c in chosen]
    rows = []
    for t in sorted(sol.uncovered):
        i = tidx[t]
        best_all = float(model.rssi[:, i].max())
        best_sel = float(model.rssi[sel_rows, i].max()) if sel_rows else float("nan")
        if best_all < thr:
            reason = "Out of range of every candidate site"
        elif best_sel >= thr:
            reason = "In range, but the serving AP is at capacity"
        else:
            reason = "Needs another AP (target or budget already reached)"
        node = g.nodes[t]
        rows.append({
            "Location": t, "Name": node["name"], "Building": node["building"],
            "Floor": int(node["floor"]), "Devices": int(node["devices"]),
            "Best signal now (dBm)": round(best_sel, 1), "Best possible (dBm)": round(best_all, 1),
            "Likely reason": reason,
        })
    return pd.DataFrame(rows, columns=["Location", "Name", "Building", "Floor", "Devices",
                                       "Best signal now (dBm)", "Best possible (dBm)", "Likely reason"])


def group_summary(plan: PlanResult, sol: Solution | None = None, by: str = "floor") -> pd.DataFrame:
    """Coverage grouped by 'floor' or 'building'."""
    sol = sol or plan.best
    g = plan.graph
    covered = set(sol.covered)
    stats: dict = {}
    for t in plan.model.targets:
        node = g.nodes[t]
        key = int(node["floor"]) if by == "floor" else (node["building"] or "(none)")
        row = stats.setdefault(key, {"total": 0, "covered": 0, "aps": 0})
        row["total"] += 1
        row["covered"] += t in covered
    for ap in sol.selected:
        node = g.nodes[ap]
        key = int(node["floor"]) if by == "floor" else (node["building"] or "(none)")
        stats.setdefault(key, {"total": 0, "covered": 0, "aps": 0})["aps"] += 1
    head = "Floor" if by == "floor" else "Building"
    rows = [{head: k, "Wi-Fi locations": v["total"], "Covered": v["covered"],
             "Coverage": f"{v['covered'] / v['total']:.1%}" if v["total"] else "n/a",
             "APs": v["aps"]} for k, v in sorted(stats.items(), key=lambda kv: str(kv[0]))]
    return pd.DataFrame(rows, columns=[head, "Wi-Fi locations", "Covered", "Coverage", "APs"])


def routes_table(plan: PlanResult) -> pd.DataFrame:
    """Cable path from the server room to each new AP (Dijkstra shortest paths)."""
    cols = ["AP", "Hops", "Length (m)", "Route"]
    if not plan.routing or not plan.routing.paths:
        return pd.DataFrame(columns=cols)
    g = plan.graph
    rows = []
    for ap, path in plan.routing.paths.items():
        length = sum(g[u][v]["distance"] for u, v in zip(path, path[1:]))
        rows.append({"AP": ap, "Hops": len(path) - 1, "Length (m)": round(length, 1),
                     "Route": " -> ".join(path)})
    return pd.DataFrame(rows, columns=cols)


def summary_dict(plan: PlanResult) -> dict:
    """Headline numbers of the deployed configuration, for the JSON download."""
    best = plan.best
    return {
        "campus": plan.campus.name,
        "mode": MODE_LABELS[plan.mode],
        "algorithm_deployed": plan.primary_label,
        "target_coverage": plan.net.target_coverage,
        "budget": plan.net.budget,
        "selected_aps": best.selected,
        "new_aps": best.new_aps,
        "coverage": round(best.coverage_pct, 4),
        "uncovered_locations": sorted(best.uncovered),
        "ap_cost": round(best.ap_cost, 2),
        "cable_length_m": round(plan.cable_length, 1),
        "cable_cost": round(plan.cable_cost, 2),
        "total_cost": round(plan.total_cost, 2),
        "initial_coverage": round(plan.initial.coverage_pct, 4),
        "random_baseline": plan.baseline,
    }


def _md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_None._"
    head = "| " + " | ".join(str(c) for c in df.columns) + " |"
    rule = "| " + " | ".join("---" for _ in df.columns) + " |"
    body = ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([head, rule, *body])


def markdown_report(plan: PlanResult) -> str:
    """A readable write-up of one optimization run, suitable for a project submission."""
    best, net, sig = plan.best, plan.net, plan.net.signal
    loc = plan.campus.locations
    b = plan.baseline
    lines = [
        f"# Wi-Fi Placement Report: {plan.campus.name}",
        f"_Generated on {date.today().isoformat()}_",
        "",
        "## 1. Campus overview",
        f"- Locations: **{len(loc)}** ({int(loc['needs_coverage'].sum())} need Wi-Fi, "
        f"{len(plan.model.candidates)} candidate AP sites, {len(plan.model.existing)} existing APs)",
        f"- Cable links: **{len(plan.campus.edges)}**, walls: **{len(plan.campus.walls)}**",
        f"- Central server room: **{plan.campus.server_id}**",
        "",
        "## 2. Settings used",
        f"- Mode: **{MODE_LABELS[plan.mode]}**; algorithm deployed: **{plan.primary_label}**",
        f"- Target coverage: {net.target_coverage:.0%}; budget (max-coverage mode): {net.budget:,.0f}",
        f"- Default AP cost: {net.ap_cost:,.0f}; AP capacity: {net.ap_capacity} devices; "
        f"cable cost: {net.cable_cost_per_m:,.2f} per metre",
        f"- Existing APs {'kept' if net.keep_existing_aps else 'reconsidered'}",
        f"- Signal model: TX {sig.tx_power_dbm:g} dBm, path loss at 1 m {sig.ref_loss_db:g} dB, "
        f"exponent {sig.path_loss_exponent:g}, threshold {sig.min_signal_dbm:g} dBm, "
        f"floor penalty {sig.floor_loss_db:g} dB, open-space radius {sig.coverage_radius_m():.1f} m",
        "",
        "## 3. Results",
        f"- Coverage: **{best.coverage_pct:.1%}** with **{len(best.selected)}** APs "
        f"({len(best.new_aps)} new) versus {plan.initial.coverage_pct:.1%} before",
        f"- AP cost **{best.ap_cost:,.0f}** + cable cost **{plan.cable_cost:,.0f}** "
        f"= total **{plan.total_cost:,.0f}**; new cable length {plan.cable_length:,.1f} m",
        f"- Uncovered Wi-Fi locations: {len(best.uncovered)}",
        "",
        "### Configurations compared",
        _md_table(solution_table(plan)),
        "",
        "### Selected access points",
        _md_table(ap_table(plan)),
        "",
        "### Coverage by floor",
        _md_table(group_summary(plan, by="floor")),
        "",
        "### Coverage by building",
        _md_table(group_summary(plan, by="building")),
        "",
        "### Cable routes (Dijkstra)",
        _md_table(routes_table(plan)),
        "",
        "### Locations still uncovered",
        _md_table(uncovered_table(plan)),
        "",
        "## 4. Why this beats guessing",
        f"Placing {b['aps']} APs at random gives {b['mean_pct']:.1%} coverage on average over "
        f"{b['trials']} trials (best trial {b['best_pct']:.1%}). The optimized layout reaches "
        f"{best.coverage_pct:.1%}.",
        "",
        "## 5. Method",
        "- **Graph theory:** the campus is a weighted undirected graph; edge weights are cable distances.",
        "- **Set cover:** each candidate AP is the set of locations it can serve above the signal threshold.",
        "- **Greedy heuristic:** repeatedly pick the AP with the best gain (or gain per cost); "
        "ln(n)-approximation.",
        "- **Integer linear programming:** binary install and coverage variables solved exactly with HiGHS.",
        "- **Dijkstra:** shortest-path tree from the server room gives the cable routes and length.",
        "",
        "## 6. Limitations",
        "This is a planning approximation using a log-distance signal model. It does not replace a "
        "professional RF site survey with measured attenuation and interference.",
        "",
    ]
    return "\n".join(lines)
