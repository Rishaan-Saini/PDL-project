"""Greedy Set Cover heuristics.

The universe is the set of Wi-Fi-needing locations; each candidate AP is a set.
  * min_ap       - unweighted greedy: pick the AP covering the most uncovered locations.
  * min_cost     - weighted greedy: pick the AP with best gain / cost ratio (cost-effectiveness).
  * max_coverage - budgeted greedy: same ratio rule, but only APs that still fit the budget.
Greedy gives a ln(n)-approximation for unweighted set cover; weighted greedy has the same
logarithmic guarantee for cost-effectiveness ratios (Chvatal / Johnson analysis).
"""
from __future__ import annotations

import time

from .coverage import CoverageModel
from .solution import Solution, evaluate, required_count


def greedy_set_cover(model: CoverageModel, mode: str, *, coverage_target: float,
                     budget: float | None = None, preselected=()) -> Solution:
    start = time.perf_counter()
    pre = list(preselected)
    n = len(model.targets)
    need = required_count(n, coverage_target)
    weighted = mode != "min_ap"

    chosen = list(pre)
    covered = set().union(*(model.sets[c] for c in chosen)) if chosen else set()
    remaining = [c for c in model.candidates if c not in set(chosen)]
    spent = 0.0
    steps: list[dict] = []

    while mode == "max_coverage" or len(covered) < need:
        best, best_score, best_gain = None, -1.0, 0
        for c in remaining:
            gain = len(model.sets[c] - covered)
            if gain == 0:
                continue
            cost = model.cost[c]
            if mode == "max_coverage" and budget is not None and spent + cost > budget + 1e-9:
                continue
            score = gain / max(cost, 1e-9) if weighted else float(gain)
            if score > best_score:
                best, best_score, best_gain = c, score, gain
        if best is None:          # nothing useful (or affordable) left
            break
        remaining.remove(best)
        chosen.append(best)
        spent += model.cost[best]
        covered |= model.sets[best]
        steps.append({
            "AP": best, "new locations": best_gain, "cost": model.cost[best],
            "total covered": len(covered),
            "coverage %": round(100 * len(covered) / n, 1) if n else 0.0,
        })

    runtime = time.perf_counter() - start
    feasible = mode == "max_coverage" or len(covered) >= need
    label = {"min_ap": "Greedy (unweighted)", "min_cost": "Greedy (cost-weighted)",
             "max_coverage": "Greedy (budgeted)"}[mode]
    return evaluate(model, chosen, algorithm=label, mode=mode, preselected=pre,
                    runtime_s=runtime, feasible=feasible, steps=steps,
                    note="" if feasible else "Target coverage not reachable with candidate sites")
