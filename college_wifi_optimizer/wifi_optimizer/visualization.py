"""Matplotlib figures: campus graph, weighted graph, coverage heatmap, cable routing and comparisons.

Figures use matplotlib.figure.Figure directly (no pyplot global state), so they are safe in Streamlit.
"""
from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Circle

from .coverage import coverage_grid

TYPE_COLORS = {
    "classroom": "#2563eb", "lab": "#7c3aed", "library": "#0d9488", "office": "#64748b",
    "reception": "#64748b", "study": "#0891b2", "auditorium": "#db2777", "cafeteria": "#ea580c",
    "corridor": "#94a3b8", "server_room": "#111827", "outdoor": "#a3a3a3",
}
COLOR_COVERED = "#16a34a"
COLOR_UNCOVERED = "#dc2626"
COLOR_NEW_AP = "#1d4ed8"
COLOR_EXISTING = "#f59e0b"
COLOR_CANDIDATE = "#7c3aed"
COLOR_ROUTE = "#0ea5e9"
COLOR_WALL = "#334155"


def _pos(graph, n):
    return graph.nodes[n]["pos"]


def _floor_nodes(graph, floor):
    return [n for n, d in graph.nodes(data=True) if d.get("floor") == floor]


def _draw_walls(ax, campus, floor):
    walls = campus.walls
    for w in walls[walls["floor"] == floor].itertuples(index=False):
        ax.plot([w.x1, w.x2], [w.y1, w.y2], color=COLOR_WALL,
                lw=2.2 if w.material == "concrete" else 1.1, solid_capstyle="round", zorder=1)


def _draw_base(ax, campus, graph, floor, weighted=False):
    nodes = _floor_nodes(graph, floor)
    sub = graph.subgraph(nodes)
    _draw_walls(ax, campus, floor)
    for u, v, d in sub.edges(data=True):
        (x1, y1), (x2, y2) = _pos(graph, u), _pos(graph, v)
        width = 1.0 + (min(d["distance"] / 12.0, 2.5) if weighted else 0.6)
        ax.plot([x1, x2], [y1, y2], color="#cbd5e1", lw=width, zorder=2)
        if weighted:
            ax.text((x1 + x2) / 2, (y1 + y2) / 2, f"{d['distance']:.0f} m", fontsize=6,
                    color="#475569", ha="center", va="center", zorder=3,
                    bbox=dict(fc="white", ec="none", pad=0.5, alpha=0.85))
    for n in nodes:
        x, y = _pos(graph, n)
        t = graph.nodes[n]["type"]
        ax.scatter([x], [y], s=55, color=TYPE_COLORS.get(t, "#64748b"),
                   marker="D" if t == "server_room" else "o", edgecolors="white",
                   linewidths=0.8, zorder=4)
        ax.annotate(n, (x, y), xytext=(4, 4), textcoords="offset points", fontsize=6.5, zorder=5)
    ax.set_aspect("equal")
    ax.set_axis_off()
    return nodes


def _draw_markers(ax, graph, floor, new_aps=(), covered=None, uncovered=None):
    nodes = set(_floor_nodes(graph, floor))
    for n in nodes:
        d = graph.nodes[n]
        x, y = _pos(graph, n)
        if d["ap_candidate"] and n not in new_aps:
            ax.scatter([x], [y], s=190, facecolors="none", edgecolors=COLOR_CANDIDATE,
                       linewidths=1.0, zorder=3)
        if d["existing_ap"]:
            ax.scatter([x], [y], s=110, marker="^", color=COLOR_EXISTING, edgecolors="white",
                       zorder=6)
    for n in new_aps:
        if n in nodes:
            x, y = _pos(graph, n)
            ax.scatter([x], [y], s=280, marker="*", color=COLOR_NEW_AP, edgecolors="white",
                       linewidths=0.6, zorder=7)
    for n in covered or ():
        if n in nodes:
            x, y = _pos(graph, n)
            ax.scatter([x], [y], s=140, facecolors="none", edgecolors=COLOR_COVERED,
                       linewidths=2.0, zorder=5)
    for n in uncovered or ():
        if n in nodes:
            x, y = _pos(graph, n)
            ax.scatter([x], [y], s=90, marker="x", color=COLOR_UNCOVERED, linewidths=2.0, zorder=5)


def _legend(ax, with_status=False):
    handles = [
        Line2D([], [], marker="o", ls="", color=TYPE_COLORS["classroom"], label="Room / location"),
        Line2D([], [], marker="o", ls="", color=TYPE_COLORS["corridor"], label="Corridor / junction"),
        Line2D([], [], marker="D", ls="", color=TYPE_COLORS["server_room"], label="Server room"),
        Line2D([], [], marker="^", ls="", color=COLOR_EXISTING, label="Existing AP"),
        Line2D([], [], marker="*", ls="", color=COLOR_NEW_AP, markersize=10, label="New AP (selected)"),
        Line2D([], [], marker="o", ls="", mfc="none", mec=COLOR_CANDIDATE, label="AP candidate site"),
        Line2D([], [], color=COLOR_WALL, lw=2, label="Wall (concrete = thick)"),
    ]
    if with_status:
        handles += [
            Line2D([], [], marker="o", ls="", mfc="none", mec=COLOR_COVERED, mew=2, label="Covered"),
            Line2D([], [], marker="x", ls="", color=COLOR_UNCOVERED, mew=2, label="Uncovered"),
        ]
    ax.legend(handles=handles, fontsize=7, loc="upper left", framealpha=0.92)


def fig_campus_graph(campus, graph, floor, weighted=False):
    """Original graph (weighted=False) or weighted graph with cable distances on every edge."""
    fig = Figure(figsize=(9, 5.4), dpi=110)
    ax = fig.add_subplot(111)
    _draw_base(ax, campus, graph, floor, weighted)
    _draw_markers(ax, graph, floor)
    ax.set_title(f"{'Weighted campus graph' if weighted else 'Campus graph'} - floor {int(floor)}",
                 fontsize=11)
    _legend(ax)
    fig.tight_layout()
    return fig


def fig_coverage(campus, graph, net, floor, aps, new_aps, covered, uncovered):
    """Best-server signal heatmap on one floor with covered / uncovered locations marked."""
    fig = Figure(figsize=(9, 5.6), dpi=110)
    ax = fig.add_subplot(111)
    X, Y, R = coverage_grid(campus, net, aps, floor)
    if aps:
        levels = np.arange(-100, -29, 5)
        cf = ax.contourf(X, Y, R, levels=levels, cmap="RdYlGn", alpha=0.55, zorder=0)
        fig.colorbar(cf, ax=ax, fraction=0.035, pad=0.02).set_label("Best signal (dBm)")
        ax.contour(X, Y, R, levels=[net.signal.min_signal_dbm], colors="#0f172a",
                   linewidths=1.2, linestyles="--", zorder=1)
    _draw_walls(ax, campus, floor)
    radius = net.signal.coverage_radius_m()
    for n in aps:
        if graph.nodes[n]["floor"] == floor:
            ax.add_patch(Circle(_pos(graph, n), radius, fill=False, ls=":", ec="#0f172a",
                                lw=0.8, zorder=1))
    _draw_markers(ax, graph, floor, new_aps=new_aps,
                  covered=[c for c in covered if graph.nodes[c]["floor"] == floor],
                  uncovered=[u for u in uncovered if graph.nodes[u]["floor"] == floor])
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_title(f"Wi-Fi coverage - floor {int(floor)} (dashed line = signal threshold)", fontsize=11)
    _legend(ax, with_status=True)
    fig.tight_layout()
    return fig


def fig_routing(campus, graph, routing, floor):
    """Shortest cable paths from the server room (Dijkstra tree) on one floor."""
    fig = Figure(figsize=(9, 5.4), dpi=110)
    ax = fig.add_subplot(111)
    _draw_base(ax, campus, graph, floor)
    if routing and routing.paths:
        for e in routing.tree_edges:
            u, v = tuple(e)
            if graph.nodes[u]["floor"] == floor and graph.nodes[v]["floor"] == floor:
                (x1, y1), (x2, y2) = _pos(graph, u), _pos(graph, v)
                ax.plot([x1, x2], [y1, y2], color=COLOR_ROUTE, lw=3.2,
                        solid_capstyle="round", zorder=3)
        sx, sy = _pos(graph, routing.server_id)
        if graph.nodes[routing.server_id]["floor"] == floor:
            ax.scatter([sx], [sy], s=150, marker="D", color="#111827", zorder=8)
        _draw_markers(ax, graph, floor, new_aps=list(routing.paths))
        ax.set_title(f"Cable routing - floor {int(floor)}: {routing.cable_length_m:,.1f} m total "
                     "(stair and riser runs between floors not drawn)", fontsize=10)
        _legend(ax)
    else:
        ax.set_title("No new APs to cable in this configuration")
    fig.tight_layout()
    return fig


def fig_comparison(entries):
    """Side-by-side bars for coverage, AP count, installation cost and runtime.

    entries: list of (label, Solution).
    """
    palette = ["#94a3b8", "#2563eb", "#16a34a", "#f59e0b"]
    fig = Figure(figsize=(11, 3.8), dpi=110)
    axes = fig.subplots(1, 4)
    labels = [name for name, _ in entries]
    metrics = [
        ("Coverage (%)", lambda s: s.coverage_pct * 100),
        ("APs in configuration", lambda s: len(s.selected)),
        ("New installation cost", lambda s: s.ap_cost),
        ("Runtime (ms)", lambda s: s.runtime_s * 1000),
    ]
    for ax, (title, fn) in zip(axes, metrics):
        vals = [fn(s) for _, s in entries]
        bars = ax.bar(labels, vals, color=palette[: len(entries)])
        ax.set_title(title, fontsize=9)
        ax.tick_params(axis="x", labelrotation=20, labelsize=7)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:,.1f}",
                    ha="center", va="bottom", fontsize=7)
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def fig_baseline(initial, best, baseline):
    """Coverage of the existing network, random placements and the optimized layout, side by side."""
    labels = ["Existing\nnetwork", "Random\n(average)", "Random\n(best of trials)", "Optimized"]
    vals = [initial.coverage_pct * 100, baseline["mean_pct"] * 100, baseline["best_pct"] * 100,
            best.coverage_pct * 100]
    colors = ["#94a3b8", "#cbd5e1", "#93c5fd", "#16a34a"]
    fig = Figure(figsize=(7.5, 3.6), dpi=110)
    ax = fig.add_subplot(111)
    bars = ax.bar(labels, vals, color=colors, width=0.62)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.2, f"{v:.1f}%", ha="center", fontsize=9)
    ax.set_ylim(0, 112)
    ax.set_ylabel("Wi-Fi locations covered (%)", fontsize=9)
    ax.set_title(f"Optimizer vs chance ({baseline['aps']} APs, {baseline['trials']} random trials)",
                 fontsize=10)
    ax.tick_params(axis="x", labelsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def fig_cost_breakdown(ap_cost, cable_cost):
    """Horizontal bars splitting the total installation cost into hardware and cabling."""
    fig = Figure(figsize=(7.5, 2.4), dpi=110)
    ax = fig.add_subplot(111)
    labels = ["AP hardware", "Cabling", "Total"]
    vals = [ap_cost, cable_cost, ap_cost + cable_cost]
    bars = ax.barh(labels, vals, color=["#2563eb", COLOR_ROUTE, "#16a34a"], height=0.55)
    top = max(vals) if max(vals) > 0 else 1.0
    for b, v in zip(bars, vals):
        ax.text(v + top * 0.015, b.get_y() + b.get_height() / 2, f"{v:,.0f}", va="center", fontsize=9)
    ax.set_xlim(0, top * 1.15)
    ax.invert_yaxis()
    ax.set_title("Installation cost breakdown", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig
