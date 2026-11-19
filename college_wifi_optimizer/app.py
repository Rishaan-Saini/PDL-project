"""Streamlit dashboard: College Wi-Fi Placement Optimizer.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from wifi_optimizer import visualization as viz
from wifi_optimizer.campus import (Campus, LOCATION_TYPES, build_graph, campus_from_json_text,
                                   candidate_ids, empty_campus, sample_campus, validate_campus)
from wifi_optimizer.config import NetworkConfig, SignalConfig
from wifi_optimizer.planner import ALGORITHM_LABELS, PlanResult, run_plan
from wifi_optimizer.solution import MODE_LABELS

st.set_page_config(page_title="Wi-Fi Placement Optimizer", page_icon="📶", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1.6rem;}
div[data-testid="stMetric"] {background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:12px 14px;}
</style>
""", unsafe_allow_html=True)

PAGES = ["Dashboard", "Campus Builder", "Network Configuration", "Optimization", "Visualization", "Analysis"]
MODE_HELP = {
    "min_ap": "Minimise the number of APs while reaching the target coverage percentage.",
    "min_cost": "Minimise total installation cost while reaching the target coverage percentage.",
    "max_coverage": "Maximise the number of covered locations without exceeding the budget.",
}
ALGO_OPTIONS = {"Greedy Set Cover": ("greedy",), "ILP (exact)": ("ilp",),
                "Compare both": ("greedy", "ilp")}


# ----------------------------------------------------------------- state helpers
def init_state():
    ss = st.session_state
    ss.setdefault("campus", sample_campus())
    ss.setdefault("net", NetworkConfig())
    ss.setdefault("plan", None)
    ss.setdefault("campus_version", 0)


def set_campus(campus: Campus):
    st.session_state.campus = campus
    st.session_state.campus_version += 1
    st.session_state.plan = None


def _valid_base():
    """Normalised campus + graph for drawing, or None if the layout is invalid."""
    campus = st.session_state.campus.normalised()
    errors = validate_campus(campus)
    if errors:
        for e in errors:
            st.error(e)
        return None
    return campus, build_graph(campus)


def _metric_block(plan: PlanResult):
    best = plan.best
    r1 = st.columns(4)
    r1[0].metric("Selected APs", len(best.selected), f"{len(best.new_aps)} new")
    r1[1].metric("Campus covered", f"{best.coverage_pct:.1%}", f"target {plan.net.target_coverage:.0%}")
    r1[2].metric("Uncovered locations", len(best.uncovered))
    r1[3].metric("Total installation cost", f"{plan.total_cost:,.0f}",
                 f"APs {best.ap_cost:,.0f} + cable {plan.cable_cost:,.0f}")
    r2 = st.columns(4)
    r2[0].metric("Total cable length (new)", f"{plan.cable_length:,.1f} m")
    r2[1].metric("Optimization time", f"{plan.total_runtime * 1000:,.1f} ms")
    r2[2].metric("Algorithm deployed", plan.primary_label)
    r2[3].metric("Initial coverage", f"{plan.initial.coverage_pct:.1%}",
                 f"{len(plan.initial.selected)} existing APs", delta_color="off")


def _solution_table(plan: PlanResult) -> pd.DataFrame:
    rows = []
    for label, sol in [("Initial (existing)", plan.initial)] + [
            (ALGORITHM_LABELS[k], s) for k, s in plan.solutions.items()]:
        rows.append({
            "Configuration": label, "APs in config": len(sol.selected),
            "New APs": len(sol.new_aps), "Coverage": f"{sol.coverage_pct:.1%}",
            "Uncovered": len(sol.uncovered), "AP cost": round(sol.ap_cost, 2),
            "Runtime (ms)": round(sol.runtime_s * 1000, 2),
            "Target met": "yes" if sol.feasible else "no", "Note": sol.note,
        })
    return pd.DataFrame(rows)


# ----------------------------------------------------------------- pages
def page_dashboard():
    campus = st.session_state.campus
    loc = campus.locations
    st.title("Campus Wi-Fi Dashboard")
    st.caption(f"Campus: {campus.name}")

    st.subheader("Campus overview")
    c = st.columns(4)
    c[0].metric("Total locations", len(loc))
    c[1].metric("Candidate AP locations", len(candidate_ids(campus)))
    c[2].metric("Locations needing Wi-Fi", int(loc["needs_coverage"].sum()))
    c[3].metric("Existing APs", int(loc["existing_ap"].sum()))

    st.subheader("Latest optimized configuration")
    plan = st.session_state.plan
    if plan is None:
        st.info("No optimization has run yet. Open **Optimization** and click *Optimize Wi-Fi Placement*.")
    else:
        _metric_block(plan)

    with st.expander("Locations by type"):
        counts = loc["type"].value_counts().rename_axis("type").reset_index(name="count")
        st.dataframe(counts, hide_index=True)


def page_builder():
    st.title("Campus Builder")
    st.caption("Edit locations, connections and walls directly in the tables. "
               "Add rows for new buildings, rooms, corridors, cables and walls.")

    b1, b2, b3 = st.columns([1, 1, 2])
    if b1.button("Load sample campus"):
        set_campus(sample_campus())
        st.rerun()
    if b2.button("Start blank campus"):
        set_campus(empty_campus())
        st.rerun()
    upload = b3.file_uploader("Import campus JSON", type=["json"])
    if upload is not None and b3.button("Import uploaded file"):
        imported, error = None, None
        try:
            imported = campus_from_json_text(upload.getvalue().decode("utf-8"))
        except (ValueError, KeyError, TypeError) as exc:
            error = str(exc)
        if error:
            st.error(f"Could not import the file: {error}")
        else:
            set_campus(imported)
            st.rerun()

    campus = st.session_state.campus
    v = st.session_state.campus_version
    campus.name = st.text_input("Campus name", value=campus.name, key=f"name_{v}")

    t1, t2, t3 = st.tabs(["Locations", "Connections (cable links)", "Walls"])
    with t1:
        campus.locations = st.data_editor(
            campus.locations, num_rows="dynamic", key=f"loc_{v}",
            column_config={
                "id": st.column_config.TextColumn("ID", required=True),
                "name": st.column_config.TextColumn("Name"),
                "type": st.column_config.SelectboxColumn("Type", options=LOCATION_TYPES),
                "building": st.column_config.TextColumn("Building"),
                "floor": st.column_config.NumberColumn("Floor", min_value=0, max_value=20, step=1),
                "x": st.column_config.NumberColumn("X (m)", step=0.5),
                "y": st.column_config.NumberColumn("Y (m)", step=0.5),
                "devices": st.column_config.NumberColumn("Device demand", min_value=0, step=1),
                "needs_coverage": st.column_config.CheckboxColumn("Needs Wi-Fi"),
                "ap_candidate": st.column_config.CheckboxColumn("AP candidate"),
                "existing_ap": st.column_config.CheckboxColumn("Existing AP"),
                "install_cost": st.column_config.NumberColumn("AP install cost", min_value=0, step=10),
            })
    with t2:
        campus.edges = st.data_editor(
            campus.edges, num_rows="dynamic", key=f"edge_{v}",
            column_config={
                "source": st.column_config.TextColumn("From (ID)", required=True),
                "target": st.column_config.TextColumn("To (ID)", required=True),
                "distance": st.column_config.NumberColumn("Cable distance (m)", min_value=0.1, step=0.5),
            })
    with t3:
        materials = list(st.session_state.net.signal.wall_materials)
        campus.walls = st.data_editor(
            campus.walls, num_rows="dynamic", key=f"wall_{v}",
            column_config={
                "floor": st.column_config.NumberColumn("Floor", min_value=0, step=1),
                "x1": st.column_config.NumberColumn("x1"), "y1": st.column_config.NumberColumn("y1"),
                "x2": st.column_config.NumberColumn("x2"), "y2": st.column_config.NumberColumn("y2"),
                "material": st.column_config.SelectboxColumn("Material", options=materials),
            })

    ids = [i for i in campus.locations["id"].tolist() if i]
    if ids:
        idx = ids.index(campus.server_id) if campus.server_id in ids else 0
        campus.server_id = st.selectbox("Central server room (cable origin)", ids, index=idx, key=f"srv_{v}")
    else:
        st.info("Add locations to choose a central server room.")

    c1, c2 = st.columns(2)
    if c1.button("Validate campus"):
        errors = validate_campus(campus.normalised())
        if errors:
            for e in errors:
                st.error(e)
        else:
            st.success("Campus is valid and every candidate AP site can be cabled from the server room.")
    c2.download_button("Download campus JSON", json.dumps(campus.to_dict(), indent=2),
                       file_name=f"{campus.name.replace(' ', '_')}.json", mime="application/json")


def page_network():
    st.title("Network Configuration")
    st.warning("This is a planning approximation for teaching and early design. It does not replace a "
               "professional RF site survey with measured attenuation and interference.")
    net = st.session_state.net
    s = net.signal

    left, right = st.columns(2)
    with left:
        st.subheader("Access point hardware and budget")
        ap_cost = st.number_input("Default AP installation cost", min_value=0.0, value=float(net.ap_cost),
                                  step=10.0, help="Used when a location's own AP cost is blank.")
        ap_capacity = st.number_input("Max devices per AP", min_value=1, value=int(net.ap_capacity), step=10)
        cable_cost = st.number_input("Cable cost per metre", min_value=0.0, value=float(net.cable_cost_per_m), step=0.5)
        target = st.slider("Target coverage (% of Wi-Fi locations)", 50, 100,
                           int(round(net.target_coverage * 100)))
        budget = st.number_input("Budget (Maximum Coverage mode)", min_value=0.0, value=float(net.budget), step=100.0)
        keep = st.checkbox("Keep existing APs in the optimized configuration", value=net.keep_existing_aps)

    with right:
        st.subheader("Signal model")
        tx = st.number_input("Transmit power (dBm)", value=float(s.tx_power_dbm), step=1.0)
        ref = st.number_input("Path loss at 1 m (dB)", value=float(s.ref_loss_db), step=1.0)
        exp = st.slider("Path-loss exponent n", 1.5, 5.0, float(s.path_loss_exponent), 0.1,
                        help="2.0 open space; 3.0-3.5 typical campus interiors.")
        thr = st.number_input("Minimum acceptable signal (dBm)", value=float(s.min_signal_dbm), step=1.0)
        floor_loss = st.number_input("Penalty per floor crossed (dB)", min_value=0.0,
                                     value=float(s.floor_loss_db), step=1.0)
        floor_h = st.number_input("Floor height (m)", min_value=0.5, value=float(s.floor_height_m), step=0.1)

    st.subheader("Wall and obstacle attenuation")
    mat_df = pd.DataFrame({"material": list(s.wall_materials),
                           "attenuation_db": list(s.wall_materials.values())})
    mat_df = st.data_editor(mat_df, num_rows="dynamic", key="materials")
    materials = {str(r.material).strip().lower(): float(r.attenuation_db)
                 for r in mat_df.dropna().itertuples() if str(r.material).strip()}

    signal = SignalConfig(tx_power_dbm=tx, ref_loss_db=ref, ref_distance_m=1.0,
                          path_loss_exponent=exp, min_signal_dbm=thr,
                          floor_height_m=floor_h, floor_loss_db=floor_loss,
                          wall_materials=materials or dict(s.wall_materials))
    net = NetworkConfig(ap_cost=ap_cost, ap_capacity=int(ap_capacity), cable_cost_per_m=cable_cost,
                        target_coverage=target / 100.0, budget=budget, keep_existing_aps=keep,
                        signal=signal)
    st.session_state.net = net

    errors = net.validate()
    for e in errors:
        st.error(e)
    c = st.columns(3)
    c[0].metric("Coverage radius (open space)", f"{signal.coverage_radius_m():.1f} m")
    c[1].metric("Signal budget", f"{tx - ref - thr:.0f} dB", help="TX power - path loss at 1 m - threshold")
    c[2].metric("Target coverage", f"{target}%")


def page_optimization():
    st.title("Optimization")
    net = st.session_state.net

    mode = st.radio("Optimization mode", list(MODE_LABELS), format_func=MODE_LABELS.get, horizontal=True)
    st.caption(MODE_HELP[mode])
    a1, a2 = st.columns([2, 1])
    algo_label = a1.selectbox("Algorithm", list(ALGO_OPTIONS), index=2)
    algorithms = ALGO_OPTIONS[algo_label]
    primary = algorithms[0]
    if len(algorithms) > 1:
        primary = a2.radio("Configuration to deploy", ["greedy", "ilp"],
                           format_func=ALGORITHM_LABELS.get, horizontal=False)

    st.write(f"Current settings: target coverage **{net.target_coverage:.0%}**, "
             f"budget **{net.budget:,.0f}**, default AP cost **{net.ap_cost:,.0f}**, "
             f"existing APs {'kept' if net.keep_existing_aps else 'reconsidered'}.")

    if st.button("Optimize Wi-Fi Placement", type="primary"):
        try:
            with st.spinner("Building coverage sets, optimising and routing cables..."):
                st.session_state.plan = run_plan(st.session_state.campus.normalised(), net, mode,
                                                 algorithms, primary)
        except ValueError as exc:
            st.session_state.plan = None
            for line in str(exc).split("\n"):
                st.error(line)

    plan = st.session_state.plan
    if plan is None:
        st.info("Click **Optimize Wi-Fi Placement** to run the selected algorithm on the current campus.")
        return
    if plan.mode != mode:
        st.warning(f"The results below come from the last run in {MODE_LABELS[plan.mode]}. "
                   "Click the button to re-run in the selected mode.")
    _metric_block(plan)
    st.subheader("Configurations compared")
    st.dataframe(_solution_table(plan), hide_index=True)
    st.caption("Greedy and ILP may choose different sites. ILP is exact for the chosen mode "
               "(within the time limit). Greedy runs in negligible time and is usually close to optimal.")


def page_visualization():
    st.title("Visualization")
    base = _valid_base()
    if base is None:
        return
    campus, graph = base
    floors = sorted({float(f) for f in campus.locations["floor"]})
    floor = st.selectbox("Floor", floors, format_func=lambda f: f"Floor {int(f)}")
    plan = st.session_state.plan

    tabs = st.tabs(["Campus graph", "Weighted graph", "Coverage & candidates",
                    "Cable routing", "Before vs after"])
    with tabs[0]:
        st.pyplot(viz.fig_campus_graph(campus, graph, floor))
    with tabs[1]:
        st.pyplot(viz.fig_campus_graph(campus, graph, floor, weighted=True))
        st.caption("Edge labels show cable distances in metres (with routing slack). These weights drive Dijkstra.")
    if plan is None:
        for t in tabs[2:]:
            with t:
                st.info("Run an optimization to see this view.")
        return

    best = plan.best
    with tabs[2]:
        st.pyplot(viz.fig_coverage(plan.campus, plan.graph, plan.net, floor, best.selected,
                                   best.new_aps, best.covered, best.uncovered))
        st.caption("Heatmap shows the best-server signal from the chosen APs, including wall and floor losses.")
    with tabs[3]:
        st.pyplot(viz.fig_routing(plan.campus, plan.graph, plan.routing, floor))
    with tabs[4]:
        st.pyplot(viz.fig_comparison([("Initial", plan.initial)] +
                                     [(ALGORITHM_LABELS[k], s) for k, s in plan.solutions.items()]))


def page_analysis():
    st.title("Analysis")
    plan = st.session_state.plan
    if plan is None:
        st.info("Run an optimization first to see the analysis.")
        return

    st.subheader("Initial vs optimized configuration")
    _metric_block(plan)
    st.dataframe(_solution_table(plan), hide_index=True)

    st.subheader("Why these APs are better than alternatives")
    b = plan.baseline
    st.write(
        f"Initial configuration covers **{plan.initial.coverage_pct:.1%}** of Wi-Fi locations. "
        f"The optimized configuration covers **{plan.best.coverage_pct:.1%}** using the same number "
        f"of APs. Random placement of **{b['aps']}** APs averages **{b['mean_pct']:.1%}** coverage "
        f"over {b['trials']} trials, and the best of those random trials reaches **{b['best_pct']:.1%}**. "
        "The optimizer is therefore doing more than luck would.")

    st.subheader("Algorithm comparison")
    st.pyplot(viz.fig_comparison([("Initial", plan.initial)] +
                                 [(ALGORITHM_LABELS[k], s) for k, s in plan.solutions.items()]))

    greedy = plan.solutions.get("greedy")
    if greedy and greedy.steps:
        st.subheader("Greedy selection order")
        st.caption("Each step picks the AP that adds the most locations per unit of cost "
                   "(or per AP in Minimum AP mode). The marginal gain explains why each AP was chosen.")
        st.dataframe(pd.DataFrame(greedy.steps), hide_index=True)

    with st.expander("Advantages and limitations"):
        st.markdown(
            "**Greedy Set Cover** is fast and simple. Its approximation ratio is about ln(n), which is "
            "near-optimal in practice on this kind of data. It can miss the global optimum because each "
            "pick is locally best.\n\n"
            "**ILP (exact)** guarantees the optimum for the chosen objective, including the budget and "
            "coverage constraints. It grows exponentially in the worst case, so it suits moderate campus "
            "sizes or a time limit with a good incumbent.\n\n"
            "**Limitations of both:** the signal model is a log-distance approximation, capacity is a "
            "greedy per-AP allocation, and cable routing uses a shortest-path tree rather than an exact "
            "Steiner tree.")

    with st.expander("How the discrete mathematics is used"):
        st.markdown(
            "- **Graph theory:** the campus is an undirected graph. Nodes are locations; edges are cable runs.\n"
            "- **Weighted graphs:** edge weights are cable distances in metres, so cost reflects real cabling.\n"
            "- **Shortest paths:** Dijkstra's algorithm builds the cheapest cable tree from the server room.\n"
            "- **Set cover:** each candidate AP is a set of locations it can serve. The goal is to cover the "
            "universe of Wi-Fi-needing locations with few or cheap sets.\n"
            "- **Combinatorial optimisation:** the ILP chooses binary AP-install variables and coverage "
            "variables under coverage and budget constraints.")


# ----------------------------------------------------------------- app shell
def main():
    init_state()
    with st.sidebar:
        st.title("📶 Wi-Fi Optimizer")
        page = st.radio("Navigate", PAGES, label_visibility="collapsed")
        st.caption("Graph theory, set cover and ILP for campus Wi-Fi planning.")
    {
        "Dashboard": page_dashboard,
        "Campus Builder": page_builder,
        "Network Configuration": page_network,
        "Optimization": page_optimization,
        "Visualization": page_visualization,
        "Analysis": page_analysis,
    }[page]()


main()
