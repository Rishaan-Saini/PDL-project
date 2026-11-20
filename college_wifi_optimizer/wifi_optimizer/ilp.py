"""Exact Integer Linear Programming formulation, solved with SciPy's HiGHS-based milp.

Decision variables
    x_j in {0,1}  : install (or keep) an AP at candidate j
    y_i in {0,1}  : location i is covered
Constraints
    y_i <= sum_{j covers i} x_j          (a location counts as covered only if some AP serves it)
    sum_i y_i >= need                    (coverage target, min-AP and min-cost modes)
    sum_j c_j x_j <= budget              (budget, max-coverage mode)
Objectives
    min sum x_j        (minimum AP)
    min sum c_j x_j    (minimum cost)
    max sum y_i        (maximum coverage)
"""
from __future__ import annotations

import time

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from .coverage import CoverageModel
from .solution import Solution, evaluate, required_count


def ilp_set_cover(model: CoverageModel, mode: str, *, coverage_target: float,
                  budget: float | None = None, preselected=(), time_limit: float = 60.0) -> Solution:
    start = time.perf_counter()
    cands, tgts = model.candidates, model.targets
    m, n = len(cands), len(tgts)
    nv = m + n
    cidx = {c: j for j, c in enumerate(cands)}
    tidx = {t: i for i, t in enumerate(tgts)}
    pre = set(preselected)
    need = required_count(n, coverage_target)
    cost = np.array([0.0 if c in pre else model.cost[c] for c in cands])

    lb = np.zeros(nv)
    ub = np.ones(nv)
    for c in pre:                       # kept existing APs are fixed to "installed"
        lb[cidx[c]] = 1.0

    obj = np.zeros(nv)                  # milp minimises, so maximise coverage via negation
    if mode == "min_ap":
        obj[:m] = [0.0 if c in pre else 1.0 for c in cands]
    elif mode == "min_cost":
        obj[:m] = cost
    else:
        obj[m:] = -1.0
        # Tie-break: among solutions with equal coverage, prefer the cheaper one. The penalty is scaled so
        # that the whole cost term stays below one covered location and never trades coverage for cost.
        total_cost = float(cost.sum())
        if total_cost > 0:
            obj[:m] = cost / (total_cost + 1.0) * 0.5

    rows, lo, hi = [], [], []
    for t in tgts:                      # linking constraints
        row = np.zeros(nv)
        row[m + tidx[t]] = 1.0
        for c in cands:
            if t in model.sets[c]:
                row[cidx[c]] = -1.0
        rows.append(row)
        lo.append(-np.inf)
        hi.append(0.0)

    if mode == "max_coverage":
        if budget is not None:
            row = np.zeros(nv)
            row[:m] = cost
            rows.append(row)
            lo.append(-np.inf)
            hi.append(float(budget))
    else:
        row = np.zeros(nv)
        row[m:] = 1.0
        rows.append(row)
        lo.append(float(need))
        hi.append(np.inf)

    A = np.vstack(rows)
    res = milp(c=obj, constraints=LinearConstraint(A, lo, hi),
               integrality=np.ones(nv), bounds=Bounds(lb, ub),
               options={"time_limit": float(time_limit)})
    runtime = time.perf_counter() - start

    if res.x is None:
        return evaluate(model, list(pre), algorithm="ILP (exact)", mode=mode, preselected=pre,
                        runtime_s=runtime, feasible=False,
                        note=f"Solver found no feasible solution: {res.message}")

    chosen = [c for c in cands if res.x[cidx[c]] > 0.5]
    covered_n = len(set().union(*(model.sets[c] for c in chosen))) if chosen else 0
    feasible = mode == "max_coverage" or covered_n >= need
    note = "Proven optimal (HiGHS)" if res.status == 0 else "Best solution found before time limit"
    return evaluate(model, chosen, algorithm="ILP (exact)", mode=mode, preselected=pre,
                    runtime_s=runtime, feasible=feasible, note=note)
