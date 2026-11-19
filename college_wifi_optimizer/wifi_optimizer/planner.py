"""End-to-end pipeline: validate -> coverage model -> algorithms -> cable routing -> baseline."""
from __future__ import annotations

import time
from dataclasses import dataclass

import networkx as nx
import numpy as np

from .campus import Campus, build_graph, validate_campus
from .config import NetworkConfig
from .coverage import CoverageModel, build_coverage_model
from .ilp import ilp_set_cover
from .routing import RoutingResult, route_cables
from .set_cover import greedy_set_cover
from .solution import MODE_LABELS, Solution, evaluate

ALGORITHM_LABELS = {"greedy": "Greedy Set Cover", "ilp": "ILP (exact)"}


@dataclass
class PlanResult:
    campus: Campus
    net: NetworkConfig
    mode: str
    graph: nx.Graph
    model: CoverageModel
    initial: Solution
    solutions: dict
    primary: str
    routing: RoutingResult | None
    baseline: dict
    build_time_s: float

    @property
    def best(self) -> Solution:
        return self.solutions[self.primary]

    @property
    def primary_label(self) -> str:
        return ALGORITHM_LABELS[self.primary]

    @property
    def cable_length(self) -> float:
        return self.routing.cable_length_m if self.routing else 0.0

    @property
    def cable_cost(self) -> float:
        return self.routing.cable_cost if self.routing else 0.0

    @property
    def total_cost(self) -> float:
        return self.best.ap_cost + self.cable_cost

    @property
    def total_runtime(self) -> float:
        return self.build_time_s + self.best.runtime_s


def random_baseline(model: CoverageModel, k: int, *, trials: int = 500, seed: int = 7,
                    preselected=()) -> dict:
    """Coverage of random placements with the same AP count: the 'why not just guess?' check."""
    rng = np.random.default_rng(seed)
    pre = list(preselected)
    base = set().union(*(model.sets[c] for c in pre)) if pre else set()
    pool = [c for c in model.candidates if c not in set(pre)]
    picks = max(0, min(k - len(pre), len(pool)))
    n = max(len(model.targets), 1)
    pcts = np.empty(trials)
    for t in range(trials):
        idx = rng.choice(len(pool), size=picks, replace=False) if picks else []
        covered = base.union(*(model.sets[pool[i]] for i in idx))
        pcts[t] = len(covered) / n
    return {"trials": trials, "aps": k, "mean_pct": float(pcts.mean()),
            "best_pct": float(pcts.max())}


def run_plan(campus: Campus, net: NetworkConfig, mode: str, algorithms=("greedy", "ilp"),
             primary: str = "greedy", time_limit: float = 60.0) -> PlanResult:
    if mode not in MODE_LABELS:
        raise ValueError(f"Unknown optimisation mode '{mode}'.")
    errors = net.validate() + validate_campus(campus)
    if errors:
        raise ValueError("\n".join(errors))

    t0 = time.perf_counter()
    graph = build_graph(campus)
    model = build_coverage_model(campus, net)
    build_time = time.perf_counter() - t0

    preselected = list(model.existing) if net.keep_existing_aps else []
    budget = net.budget if mode == "max_coverage" else None
    initial = evaluate(model, model.existing, algorithm="Initial (existing APs)", mode="current",
                       preselected=model.existing, runtime_s=0.0, feasible=True,
                       note="Access points already installed")

    solutions: dict[str, Solution] = {}
    for key in algorithms:
        if key == "greedy":
            solutions[key] = greedy_set_cover(model, mode, coverage_target=net.target_coverage,
                                              budget=budget, preselected=preselected)
        elif key == "ilp":
            solutions[key] = ilp_set_cover(model, mode, coverage_target=net.target_coverage, budget=budget,
                                  preselected=preselected, time_limit=time_limit)
        else:
            raise ValueError(f"Unknown algorithm '{key}'.")

    if primary not in solutions:
        primary = next(iter(solutions))
    best = solutions[primary]
    routing = (route_cables(graph, campus.server_id, best.new_aps, net.cable_cost_per_m)
               if best.new_aps else None)
    baseline = random_baseline(model, len(best.selected), preselected=preselected)

    return PlanResult(campus=campus, net=net, mode=mode, graph=graph, model=model,
                      initial=initial, solutions=solutions, primary=primary, routing=routing,
                      baseline=baseline, build_time_s=build_time)
