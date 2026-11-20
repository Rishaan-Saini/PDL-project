"""Streamlit dashboard: College Wi-Fi Placement Optimizer.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from wifi_optimizer import report
from wifi_optimizer import visualization as viz
from wifi_optimizer.campus import (Campus, LOCATION_TYPES, build_graph, campus_from_json_text,
                                   candidate_ids, empty_campus, sample_campus, validate_campus)
from wifi_optimizer.config import NetworkConfig, SignalConfig
from wifi_optimizer.planner import ALGORITHM_LABELS, PlanResult, run_plan
from wifi_optimizer.solution import MODE_LABELS

st.set_page_config(page_title="Wi-Fi Placement Optimizer", page_icon="📶", layout="wide")

PAGES = {
    "🏠 Dashboard": "dashboard",
    "🏫 Campus Builder": "builder",
    "⚙️ Network Configuration": "network",
    "🚀 Optimization": "optimization",
    "🗺️ Visualization": "visualization",
    "📊 Analysis": "analysis",
    "📄 Report & Export": "report",
}
MODE_HELP = {
    "min_ap": "Minimise the number of APs while reaching the target coverage percentage.",
    "min_cost": "Minimise total installation cost while reaching the target coverage percentage.",
    "max_coverage": "Maximise the number of covered locations without exceeding the budget.",
}
ALGO_OPTIONS = {"Greedy Set Cover": ("greedy",), "ILP (exact)": ("ilp",),
                "Compare both": ("greedy", "ilp")}

PRESETS = {
    "Economy": dict(target=0.85, budget=1500.0, ap_cost=100.0, min_signal=-72.0),
    "Balanced": dict(target=0.95, budget=2500.0, ap_cost=150.0, min_signal=-70.0),
    "High performance": dict(target=1.00, budget=4500.0, ap_cost=220.0, min_signal=-65.0),
}

CSS = """
<style>
.block-container {padding-top: 1.2rem; max-width: 1280px;}
footer {visibility: hidden;}
section[data-testid="stSidebar"] {background: #f8fafc; border-right: 1px solid #e2e8f0;}

.hero {background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 55%, #0ea5e9 100%);
       color: #ffffff; padding: 24px 30px; border-radius: 16px; margin-bottom: 18px;
       box-shadow: 0 8px 24px rgba(37, 99, 235, 0.22);}
.hero-title {font-size: 1.85rem; font-weight: 750; line-height: 1.2; margin: 0;}
.hero-sub {color: #dbeafe; font-size: 1.0rem; margin-top: 6px;}

.brand {font-size: 1.25rem; font-weight: 750; color: #1e3a8a; margin-bottom: 2px;}
.brand-sub {color: #64748b; font-size: 0.82rem; margin-bottom: 10px;}

div[data-testid="stMetric"] {background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
       padding: 12px 14px; box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);}
div[data-testid="stMetricLabel"] {color: #475569;}

.step-card {background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
            padding: 12px 14px; margin-bottom: 10px; display: flex; gap: 12px; align-items: flex-start;}
.step-num {background: #2563eb; color: #ffffff; border-radius: 50%; min-width: 28px; height: 28px;
           display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.9rem;}
.step-title {font-weight: 650; color: #0f172a;}
.step-text {color: #64748b; font-size: 0.88rem;}

.pill {display: inline-block; padding: 3px 11px; border-radius: 999px; font-size: 0.8rem;
       font-weight: 600; margin: 0 6px 6px 0;}
.pill-ok {background: #dcfce7; color: #166534;}
.pill-warn {background: #fef3c7; color: #92400e;}
.pill-info {background: #dbeafe; color: #1e40af;}
.pill-muted {background: #f1f5f9; color: #475569;}

.stButton > button[kind="primary"] {font-weight: 650;}
</style>
"""


# ----------------------------------------------------------------- state helpers
def init_state():
    ss = st.session_state
    ss.setdefault("campus", sample_campus())
    ss.setdefault("net", NetworkConfig())
    ss.setdefault("plan", None)
    ss.setdefault("plan_sig", None)
    ss.setdefault("campus_version", 0)
    ss.setdefault("nav", "🏠 Dashboard")


def set_campus(campus: Campus):
    st.session_state.campus = campus
    st.session_state.campus_version += 1
    st.session_state.plan = None
    st.session_state.plan_sig = None


def goto(page_label: str):
    """Button callback: jump to another page (runs before the sidebar radio is drawn)."""
    st.session_state.nav = page_label


def _valid_base():
    """Normalised campus + graph for drawing, or None if the layout is invalid."""
    campus = st.session_state.campus.normalised()
    errors = validate_campus(campus)
    if errors:
        for e in errors:
            st.error(e)
        return None
    return campus, build_graph(campus)


def _execute_plan(mode: str, algorithms: tuple, primary: str) -> bool:
    """Run the optimizer and store the result. Returns True on success."""
    campus = st.session_state.campus
    try:
        with st.spinner("Building coverage sets, optimising and routing cables..."):
            st.session_state.plan = run_plan(campus.normalised(), st.session_state.net, mode,
                                             algorithms, primary)
        st.session_state.plan_sig = report.campus_signature(campus)
        return True
    except ValueError as exc:
        st.session_state.plan = None
        st.session_state.plan_sig = None
        for line in str(exc).split("\n"):
            st.error(line)
        return False


# ----------------------------------------------------------------- shared UI pieces
def page_header(title: str, subtitle: str = ""):
    sub = f'<div class="hero-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(f'<div class="hero"><div class="hero-title">{title}</div>{sub}</div>',
                unsafe_allow_html=True)


def pill(text: str, kind: str = "info") -> str:
    return f'<span class="pill pill-{kind}">{text}</span>'


def stale_notice(plan: PlanResult | None):
    """Warn when the campus or settings changed after the displayed optimization was run."""
    if plan is None:
        return
    reasons = []
    if st.session_state.get("plan_sig") != report.campus_signature(st.session_state.campus):
        reasons.append("the campus layout was edited")
    if plan.net != st.session_state.net:
        reasons.append("the network settings changed")
    if reasons:
        st.warning("These results are out of date because " + " and ".join(reasons) +
                   " after the last run. Open **Optimization** and run it again.")


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
    if not best.feasible:
        st.warning(f"The target was not reached: {best.note or 'see the configuration table.'}")


def _draw_floors(make_fig, floors, show_all: bool, selected_floor: float):
    for f in (floors if show_all else [selected_floor]):
        st.pyplot(make_fig(f))


# ----------------------------------------------------------------- pages
def page_dashboard():
    campus = st.session_state.campus
    loc = campus.locations
    page_header("Campus Wi-Fi Placement Optimizer",
                f"Plan access point locations for <b>{campus.name}</b> using graph theory, "
                "set cover and integer linear programming.")

    errors = validate_campus(campus.normalised())
    plan = st.session_state.plan
    pills = pill("Campus valid", "ok") if not errors else pill(f"{len(errors)} layout issue(s)", "warn")
    pills += pill("Optimization ready", "ok") if plan else pill("Not optimized yet", "muted")
    st.markdown(pills, unsafe_allow_html=True)
    if errors:
        with st.expander("Layout issues to fix in the Campus Builder"):
            for e in errors:
                st.write("- " + e)

    st.subheader("Campus overview")
    c = st.columns(4)
    c[0].metric("Total locations", len(loc))
    c[1].metric("Candidate AP locations", len(candidate_ids(campus)))
    c[2].metric("Locations needing Wi-Fi", int(loc["needs_coverage"].sum()))
    c[3].metric("Existing APs", int(loc["existing_ap"].sum()))

    left, right = st.columns([3, 2])
    with left:
        st.subheader("How it works")
        steps = [
            ("Describe the campus", "Edit locations, cable links and walls, or import a JSON layout."),
            ("Tune the network", "Set AP cost, capacity, target coverage, budget and the signal model."),
            ("Optimize", "Greedy set cover and an exact ILP choose where the new APs go."),
            ("Review and export", "Inspect maps, heatmaps and cable routes, then download the report."),
        ]
        for i, (title, text) in enumerate(steps, 1):
            st.markdown(f'<div class="step-card"><div class="step-num">{i}</div><div>'
                        f'<div class="step-title">{title}</div><div class="step-text">{text}</div>'
                        '</div></div>', unsafe_allow_html=True)
    with right:
        st.subheader("Locations by type")
        if loc.empty:
            st.info("The campus has no locations yet.")
        else:
            counts = loc["type"].value_counts().rename_axis("type").to_frame("locations")
            st.bar_chart(counts)

    st.subheader("Get started")
    b = st.columns(3)
    b[0].button("Edit the campus", on_click=goto, args=("🏫 Campus Builder",))
    b[1].button("Configure the network", on_click=goto, args=("⚙️ Network Configuration",))
    if b[2].button("Run a quick demo optimization", type="primary", disabled=bool(errors)):
        if _execute_plan("min_cost", ("greedy", "ilp"), "greedy"):
            st.success("Done. Scroll down for the result or open Visualization and Analysis.")
            plan = st.session_state.plan

    if not errors:
        st.subheader("Campus map")
        base = _valid_base()
        if base is not None:
            valid_campus, graph = base
            floors = sorted({float(f) for f in valid_campus.locations["floor"]})
            floor = st.selectbox("Floor", floors, format_func=lambda f: f"Floor {int(f)}", key="dash_floor")
            st.pyplot(viz.fig_campus_graph(valid_campus, graph, floor))

    st.subheader("Latest optimized configuration")
    if plan is None:
        st.info("No optimization has run yet. Open **Optimization**, or press the demo button above.")
    else:
        stale_notice(plan)
        _metric_block(plan)


def page_builder():
    page_header("Campus Builder", "Edit locations, connections and walls directly in the tables. "
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
        except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
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
        st.caption("Tick **Needs Wi-Fi** for places that must be covered and **AP candidate** for places "
                   "where an access point may be mounted. Leave the AP install cost blank to use the default.")
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
        st.caption("Each row is a cable run between two location IDs, with its length in metres.")
        campus.edges = st.data_editor(
            campus.edges, num_rows="dynamic", key=f"edge_{v}",
            column_config={
                "source": st.column_config.TextColumn("From (ID)", required=True),
                "target": st.column_config.TextColumn("To (ID)", required=True),
                "distance": st.column_config.NumberColumn("Cable distance (m)", min_value=0.1, step=0.5),
            })
    with t3:
        st.caption("Walls are line segments on one floor. Thicker materials block more signal.")
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

    if st.checkbox("Show live layout preview", key=f"preview_{v}"):
        base = _valid_base()
        if base is not None:
            valid_campus, graph = base
            floors = sorted({float(f) for f in valid_campus.locations["floor"]})
            floor = st.selectbox("Preview floor", floors, format_func=lambda f: f"Floor {int(f)}",
                                 key=f"prev_floor_{v}")
            st.pyplot(viz.fig_campus_graph(valid_campus, graph, floor))


def _apply_preset(name: str):
    """Button callback: overwrite the key settings with a preset."""
    p = PRESETS[name]
    cur = st.session_state.net
    st.session_state.net = NetworkConfig(
        ap_cost=p["ap_cost"], ap_capacity=cur.ap_capacity, cable_cost_per_m=cur.cable_cost_per_m,
        target_coverage=p["target"], budget=p["budget"], keep_existing_aps=cur.keep_existing_aps,
        signal=SignalConfig(tx_power_dbm=cur.signal.tx_power_dbm, ref_loss_db=cur.signal.ref_loss_db,
                            ref_distance_m=cur.signal.ref_distance_m,
                            path_loss_exponent=cur.signal.path_loss_exponent,
                            min_signal_dbm=p["min_signal"], floor_height_m=cur.signal.floor_height_m,
                            floor_loss_db=cur.signal.floor_loss_db,
                            wall_materials=dict(cur.signal.wall_materials)))


def _reset_net():
    st.session_state.net = NetworkConfig()


def page_network():
    page_header("Network Configuration", "Hardware, budget and the radio signal model behind the plan.")
    st.warning("This is a planning approximation for teaching and early design. It does not replace a "
               "professional RF site survey with measured attenuation and interference.")
    net = st.session_state.net
    s = net.signal

    st.caption("Quick presets (you can still fine-tune every value afterwards)")
    pc = st.columns(len(PRESETS) + 1)
    for col, name in zip(pc, PRESETS):
        col.button(name, on_click=_apply_preset, args=(name,), key=f"preset_{name}")
    pc[-1].button("Reset to defaults", on_click=_reset_net)

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


def _downloads(plan: PlanResult, key: str):
    d = st.columns(3)
    d[0].download_button("Download AP table (CSV)", report.ap_table(plan).to_csv(index=False),
                         file_name="selected_access_points.csv", mime="text/csv", key=f"{key}_csv")
    d[1].download_button("Download summary (JSON)", json.dumps(report.summary_dict(plan), indent=2),
                         file_name="optimization_summary.json", mime="application/json", key=f"{key}_json")
    d[2].download_button("Download report (Markdown)", report.markdown_report(plan),
                         file_name="wifi_placement_report.md", mime="text/markdown", key=f"{key}_md")


def page_optimization():
    page_header("Optimization", "Choose what to optimise for, run the algorithms and inspect the result.")
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

    with st.container(border=True):
        st.markdown(f"**Current settings:** target coverage **{net.target_coverage:.0%}**, "
                    f"budget **{net.budget:,.0f}**, default AP cost **{net.ap_cost:,.0f}**, "
                    f"existing APs {'kept' if net.keep_existing_aps else 'reconsidered'}. "
                    "Change them in *Network Configuration*.")

    if st.button("Optimize Wi-Fi Placement", type="primary"):
        _execute_plan(mode, algorithms, primary)

    plan = st.session_state.plan
    if plan is None:
        st.info("Click **Optimize Wi-Fi Placement** to run the selected algorithm on the current campus.")
        return
    stale_notice(plan)
    if plan.mode != mode:
        st.warning(f"The results below come from the last run in {MODE_LABELS[plan.mode]}. "
                   "Click the button to re-run in the selected mode.")
    _metric_block(plan)

    t = st.tabs(["Configurations compared", "Selected access points", "Cable routes", "Uncovered locations"])
    with t[0]:
        st.dataframe(report.solution_table(plan), hide_index=True)
        st.caption("Greedy and ILP may choose different sites. ILP is exact for the chosen mode "
                   "(within the time limit). Greedy runs in negligible time and is usually close to optimal.")
    with t[1]:
        st.dataframe(report.ap_table(plan), hide_index=True)
    with t[2]:
        routes = report.routes_table(plan)
        if routes.empty:
            st.info("No new APs need cabling in this configuration.")
        else:
            st.dataframe(routes, hide_index=True)
    with t[3]:
        unc = report.uncovered_table(plan)
        if unc.empty:
            st.success("Every location that needs Wi-Fi is covered.")
        else:
            st.dataframe(unc, hide_index=True)
    _downloads(plan, "opt")


def page_visualization():
    page_header("Visualization", "Graphs, signal heatmaps and cable routes, floor by floor.")
    base = _valid_base()
    if base is None:
        return
    campus, graph = base
    floors = sorted({float(f) for f in campus.locations["floor"]})
    f1, f2 = st.columns([2, 1])
    floor = f1.selectbox("Floor", floors, format_func=lambda f: f"Floor {int(f)}")
    show_all = f2.checkbox("Show all floors", value=False)
    plan = st.session_state.plan

    tabs = st.tabs(["Campus graph", "Weighted graph", "Coverage & candidates",
                    "Cable routing", "Before vs after"])
    with tabs[0]:
        _draw_floors(lambda f: viz.fig_campus_graph(campus, graph, f), floors, show_all, floor)
    with tabs[1]:
        _draw_floors(lambda f: viz.fig_campus_graph(campus, graph, f, weighted=True), floors, show_all, floor)
        st.caption("Edge labels show cable distances in metres (with routing slack). These weights drive Dijkstra.")
    if plan is None:
        for t in tabs[2:]:
            with t:
                st.info("Run an optimization to see this view.")
        return

    stale_notice(plan)
    best = plan.best
    with tabs[2]:
        _draw_floors(lambda f: viz.fig_coverage(plan.campus, plan.graph, plan.net, f, best.selected,
                                                best.new_aps, best.covered, best.uncovered),
                     floors, show_all, floor)
        st.caption("Heatmap shows the best-server signal from the chosen APs, including wall and floor losses.")
    with tabs[3]:
        _draw_floors(lambda f: viz.fig_routing(plan.campus, plan.graph, plan.routing, f),
                     floors, show_all, floor)
    with tabs[4]:
        st.pyplot(viz.fig_comparison([("Initial", plan.initial)] +
                                     [(ALGORITHM_LABELS[k], s) for k, s in plan.solutions.items()]))


def page_analysis():
    page_header("Analysis", "Why the chosen access points are a good answer, and where the gaps are.")
    plan = st.session_state.plan
    if plan is None:
        st.info("Run an optimization first to see the analysis.")
        return
    stale_notice(plan)

    st.subheader("Initial vs optimized configuration")
    _metric_block(plan)
    st.dataframe(report.solution_table(plan), hide_index=True)

    st.subheader("Why these APs are better than alternatives")
    b = plan.baseline
    st.write(
        f"Initial configuration covers **{plan.initial.coverage_pct:.1%}** of Wi-Fi locations. "
        f"The optimized configuration covers **{plan.best.coverage_pct:.1%}** using the same number "
        f"of APs. Random placement of **{b['aps']}** APs averages **{b['mean_pct']:.1%}** coverage "
        f"over {b['trials']} trials, and the best of those random trials reaches **{b['best_pct']:.1%}**. "
        "The optimizer is therefore doing more than luck would.")
    g1, g2 = st.columns(2)
    g1.pyplot(viz.fig_baseline(plan.initial, plan.best, plan.baseline))
    g2.pyplot(viz.fig_cost_breakdown(plan.best.ap_cost, plan.cable_cost))

    st.subheader("Coverage by floor and by building")
    s1, s2 = st.columns(2)
    s1.dataframe(report.group_summary(plan, by="floor"), hide_index=True)
    s2.dataframe(report.group_summary(plan, by="building"), hide_index=True)

    st.subheader("Algorithm comparison")
    st.pyplot(viz.fig_comparison([("Initial", plan.initial)] +
                                 [(ALGORITHM_LABELS[k], s) for k, s in plan.solutions.items()]))

    greedy = plan.solutions.get("greedy")
    if greedy and greedy.steps:
        st.subheader("Greedy selection order")
        st.caption("Each step picks the AP that adds the most locations per unit of cost "
                   "(or per AP in Minimum AP mode). The marginal gain explains why each AP was chosen.")
        st.dataframe(pd.DataFrame(greedy.steps), hide_index=True)

    unc = report.uncovered_table(plan)
    if not unc.empty:
        st.subheader("Locations still uncovered")
        st.dataframe(unc, hide_index=True)

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


def page_report():
    page_header("Report & Export", "A ready-to-submit written summary of the latest optimization run.")
    plan = st.session_state.plan
    if plan is None:
        st.info("Run an optimization first. The report is generated from its results.")
        st.button("Go to Optimization", on_click=goto, args=("🚀 Optimization",))
        return
    stale_notice(plan)
    _downloads(plan, "rep")
    st.divider()
    st.markdown(report.markdown_report(plan))


# ----------------------------------------------------------------- app shell
PAGE_FUNCS = {
    "dashboard": page_dashboard, "builder": page_builder, "network": page_network,
    "optimization": page_optimization, "visualization": page_visualization,
    "analysis": page_analysis, "report": page_report,
}


def sidebar():
    with st.sidebar:
        st.markdown('<div class="brand">📶 Wi-Fi Optimizer</div>'
                    '<div class="brand-sub">Graph theory, set cover and ILP for campus Wi-Fi planning.</div>',
                    unsafe_allow_html=True)
        st.radio("Navigate", list(PAGES), key="nav", label_visibility="collapsed")
        st.divider()
        campus = st.session_state.campus
        plan = st.session_state.plan
        st.caption(f"**Campus:** {campus.name}")
        st.caption(f"**Locations:** {len(campus.locations)}")
        if plan is None:
            st.markdown(pill("Not optimized yet", "muted"), unsafe_allow_html=True)
        else:
            st.markdown(pill(f"{plan.best.coverage_pct:.0%} covered", "ok") +
                        pill(f"{len(plan.best.selected)} APs", "info"), unsafe_allow_html=True)


def main():
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()
    sidebar()
    PAGE_FUNCS[PAGES[st.session_state.nav]]()


main()
