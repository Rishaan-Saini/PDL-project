# College Wi-Fi Placement Optimizer

An interactive planning tool that decides where to install Wi-Fi access points (APs) on a campus so that the
most important locations are covered for the least money. It combines graph theory, set cover, integer
linear programming and shortest-path cable routing, with a Streamlit dashboard and Matplotlib visualisations.

> This is a **planning approximation** for design and teaching. It is not a replacement for a professional
> RF site survey, which measures real attenuation and interference.

## Features

| Area | What it does |
|---|---|
| Campus builder | Edit locations (rooms, labs, corridors, outdoor junctions), cable links and walls in tables; import/export JSON |
| Signal model | Log-distance path loss, wall attenuation via segment intersection, floor penalty, configurable threshold |
| Coverage sets | Each candidate AP becomes a set of locations it can serve, with a capacity limit |
| Greedy set cover | Unweighted (min AP), cost-weighted (min cost) and budgeted (max coverage) |
| ILP | Exact integer programs for the same three modes, solved with SciPy's HiGHS `milp` |
| Cable routing | Dijkstra shortest-path tree from the server room to each new AP (NetworkX) |
| Baseline | 500 random placements with the same AP count, to show the optimizer beats chance |
| Visualisation | Campus graph, weighted graph, coverage heatmap, cable routes, before/after and algorithm comparisons |

## Project structure

```
college_wifi_optimizer/
├── app.py                      # Streamlit dashboard (6 pages)
├── requirements.txt
├── README.md
├── data/
│   └── sample_campus.json      # sample campus (exported from wifi_optimizer/sample_data.py)
└── wifi_optimizer/
    ├── __init__.py
    ├── config.py               # SignalConfig and NetworkConfig dataclasses
    ├── campus.py               # Campus model, validation, NetworkX graph construction
    ├── sample_data.py          # built-in sample campus generator
    ├── coverage.py             # NumPy signal model and coverage sets (set-cover instance)
    ├── solution.py             # Solution container and evaluation
    ├── set_cover.py            # greedy set cover heuristics
    ├── ilp.py                  # exact ILP formulation (SciPy milp)
    ├── routing.py              # Dijkstra cable routing
    ├── planner.py              # end-to-end pipeline and random baseline
    └── visualization.py        # Matplotlib figures
```

## Installation

Requires Python 3.9 or newer. Works on Windows and Linux.

**Windows (PowerShell or Command Prompt)**
```bat
cd college_wifi_optimizer
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Linux / macOS**
```bash
cd college_wifi_optimizer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
streamlit run app.py
```

Open the URL shown in the terminal (usually http://localhost:8501). The sample campus loads immediately.

Optional: regenerate the sample JSON with `python -m wifi_optimizer.sample_data data/sample_campus.json`.

### Quick walkthrough
1. **Dashboard**: overview of the campus.
2. **Campus Builder**: edit or import a layout. Use **Validate campus** to check it.
3. **Network Configuration**: set AP cost, capacity, cable cost, target coverage, budget and signal parameters.
4. **Optimization**: pick a mode and algorithm, then click **Optimize Wi-Fi Placement**.
5. **Visualization**: view graphs, heatmaps and routes per floor.
6. **Analysis**: compare initial vs optimized, algorithm results, greedy steps and random baseline.

## Algorithms and the mathematics behind them

**Graph model.** The campus is an undirected weighted graph G = (V, E). Nodes are locations with coordinates,
floor and type. Edge weights are cable distances (3-D Euclidean times a 1.15 routing slack).

**Signal model.** For AP j and location i on floors f_j and f_i:

    RSSI = P_tx - [PL(d0) + 10 n log10(d / d0)] - floor_loss |f_j - f_i| - sum over walls crossed of att_k

Walls are line segments. A wall counts only when the AP-to-point segment properly intersects it (orientation
test) and both endpoints lie on the wall's floor. The coverage radius with no obstacles is
r = d0 * 10^((P_tx - PL(d0) - threshold) / (10 n)).

**Set cover.** The universe U is the set of locations needing Wi-Fi. Each candidate AP j defines S_j, the set of
locations it can serve above the threshold, after a capacity limit (strongest signals served first).
Let `need = ceil(target * |U|)`.

- *Greedy, minimum AP:* repeatedly add the AP with the largest |S_j \ covered|. This gives a ln(|U|)
  approximation for unweighted set cover.
- *Greedy, minimum cost:* repeatedly add the AP with the best ratio |S_j \ covered| / c_j
  (cost-effectiveness). Costs are per candidate and can differ.
- *Greedy, maximum coverage:* the same ratio rule, but only APs that still fit the budget.

**ILP.** Binary variables x_j (install AP j) and y_i (location i covered):

    min  sum x_j                                  (minimum AP)
    min  sum c_j x_j                              (minimum cost)
    max  sum y_i   s.t.  sum c_j x_j <= B         (maximum coverage)
    s.t.  y_i <= sum_{j : i in S_j} x_j           for every location i
          sum_i y_i >= need                       (min AP / min cost)

Kept existing APs are fixed to x_j = 1 and carry no new installation cost.

**Dijkstra routing.** `nx.single_source_dijkstra` from the server room, weighted by cable distance, gives a
shortest-path tree. The cable length is the total length of the tree's edges, so shared trunks are counted
once. This is a good approximation to the Steiner tree, which is NP-hard to compute exactly.

**Random baseline.** Random placements with the same AP count estimate how much better the optimizer is than
chance.

### Advantages and limitations

| | Greedy set cover | ILP (exact) |
|---|---|---|
| Speed | Near-instant | Fast here; exponential in the worst case, so use a time limit for large campuses |
| Quality | Usually near-optimal; can miss the global optimum | Proven optimal for the chosen objective (within the time limit) |
| Constraints | Coverage target and budget, handled heuristically | Exact handling of coverage, budget and fixed APs |
| Use case | Interactive what-if analysis, large campuses | Final planning and certification of an optimum |

Limitations shared by both: the signal model is an approximation, capacity is applied per AP with a simple
strongest-signal rule, and routing uses a shortest-path tree rather than an optimal Steiner tree.

## Validation and error handling

- The campus is validated before every run: unique IDs, numeric coordinates, edges that reference real IDs,
  positive distances, a server room, at least one candidate, and a cable route from the server to every candidate.
- Invalid configuration (negative costs, zero exponent, target outside 0-100%) is reported in the UI without
  crashing.
- ILP infeasibility (for example, a 100% target that cannot be reached) is reported in the results table.

## Notes for extension

- Add a new mode: write a greedy variant in `set_cover.py` and a matching objective in `ilp.py`.
- Replace the signal model: change only `rssi_matrix` in `coverage.py`. Everything downstream uses the coverage sets.
- Add per-AP capacity as an assignment model: introduce assignment variables z_ij and the constraint
  sum_i d_i z_ij <= C x_j in `ilp.py`.
