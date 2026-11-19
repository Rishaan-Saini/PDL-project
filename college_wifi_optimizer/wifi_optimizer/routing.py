"""Cable routing with Dijkstra's shortest-path algorithm (NetworkX).

Dijkstra from the server room yields a shortest-path TREE. The union of the paths to the new
APs is that tree, so shared trunk segments are counted once in the total cable length.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx


@dataclass
class RoutingResult:
    server_id: str
    paths: dict = field(default_factory=dict)        # AP id -> node list from server to AP
    tree_edges: set = field(default_factory=set)     # frozenset({u, v}) cable segments used
    cable_length_m: float = 0.0
    cable_cost: float = 0.0


def route_cables(graph: nx.Graph, server_id: str, ap_ids, cable_cost_per_m: float) -> RoutingResult:
    # Dijkstra's algorithm: single-source shortest paths weighted by cable distance.
    _, paths = nx.single_source_dijkstra(graph, server_id, weight="distance")
    result = RoutingResult(server_id=server_id)
    for ap in ap_ids:
        if ap not in paths:
            raise ValueError(f"No cable route from {server_id} to {ap}.")
        result.paths[ap] = paths[ap]
        for u, v in zip(paths[ap], paths[ap][1:]):
            result.tree_edges.add(frozenset((u, v)))
    result.cable_length_m = sum(graph[u][v]["distance"]
                                for u, v in (tuple(e) for e in result.tree_edges))
    result.cable_cost = result.cable_length_m * cable_cost_per_m
    return result
