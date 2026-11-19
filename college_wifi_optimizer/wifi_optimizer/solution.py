"""Common result container shared by the greedy and ILP solvers."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .coverage import CoverageModel

MODE_LABELS = {
    "min_ap": "Minimum AP Mode",
    "min_cost": "Minimum Cost Mode",
    "max_coverage": "Maximum Coverage Mode",
}


def required_count(n_targets: int, coverage_target: float) -> int:
    """Smallest integer number of covered locations that meets the target percentage."""
    if n_targets == 0:
        return 0
    return max(1, math.ceil(coverage_target * n_targets - 1e-9))


@dataclass
class Solution:
    algorithm: str
    mode: str
    selected: list[str]            # all APs in the final configuration (kept existing + new)
    new_aps: list[str]             # APs that must be purchased and cabled
    covered: frozenset
    uncovered: frozenset
    coverage_pct: float            # fraction in [0, 1]
    ap_cost: float                 # hardware cost of new APs
    runtime_s: float
    feasible: bool
    steps: list[dict] = field(default_factory=list)
    note: str = ""


def evaluate(model: CoverageModel, selected, *, algorithm: str, mode: str, preselected,
             runtime_s: float, feasible: bool, steps=None, note: str = "") -> Solution:
    """Turn a list of chosen APs into a Solution with coverage and cost metrics."""
    selected = list(dict.fromkeys(selected))
    pre = set(preselected)
    covered = frozenset().union(*(model.sets[c] for c in selected)) if selected else frozenset()
    targets = frozenset(model.targets)
    new_aps = [c for c in selected if c not in pre]
    cost = sum(model.cost[c] for c in new_aps)
    pct = len(covered) / len(targets) if targets else 0.0
    return Solution(
        algorithm=algorithm, mode=mode, selected=selected, new_aps=new_aps,
        covered=covered, uncovered=targets - covered, coverage_pct=pct, ap_cost=cost,
        runtime_s=runtime_s, feasible=feasible, steps=steps or [], note=note,
    )
