"""Signal-strength model (NumPy-vectorised) and the candidate-to-location coverage sets.

Each candidate AP defines a SET of locations it can serve. This is the input to Set Cover.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .campus import Campus
from .config import NetworkConfig, SignalConfig


def _segment_crossings(p1, p2, w1, w2):
    """Boolean tensor (m, n, k): True where the segment p1[i] -> p2[j] properly crosses wall k.

    Uses orientation (cross-product) tests broadcast over all AP x point x wall triples.
    """
    A = p1[:, None, None, :]
    B = p2[None, :, None, :]
    C = w1[None, None, :, :]
    D = w2[None, None, :, :]

    def cross(o, a, b):
        return ((a[..., 0] - o[..., 0]) * (b[..., 1] - o[..., 1])
                - (a[..., 1] - o[..., 1]) * (b[..., 0] - o[..., 0]))

    d1 = cross(A, B, C)
    d2 = cross(A, B, D)
    d3 = cross(C, D, A)
    d4 = cross(C, D, B)
    return (d1 * d2 < 0) & (d3 * d4 < 0)


def rssi_matrix(tx_xy, tx_floor, rx_xy, rx_floor, walls_xy, wall_floor, wall_att, sig: SignalConfig):
    """Received signal strength (dBm) for every transmitter (rows) and receiver (columns)."""
    dxy = tx_xy[:, None, :] - rx_xy[None, :, :]
    dz = (tx_floor[:, None] - rx_floor[None, :]) * sig.floor_height_m
    dist = np.sqrt((dxy ** 2).sum(axis=-1) + dz ** 2)
    dist = np.maximum(dist, sig.ref_distance_m)
    path_loss = sig.ref_loss_db + 10.0 * sig.path_loss_exponent * np.log10(dist / sig.ref_distance_m)
    floor_pen = sig.floor_loss_db * np.abs(tx_floor[:, None] - rx_floor[None, :])

    wall_pen = np.zeros_like(path_loss)
    if len(wall_att):
        crossing = _segment_crossings(tx_xy, rx_xy, walls_xy[:, 0, :], walls_xy[:, 1, :])
        same_floor = ((wall_floor[None, None, :] == tx_floor[:, None, None])
                      & (wall_floor[None, None, :] == rx_floor[None, :, None]))
        wall_pen = ((crossing & same_floor) * wall_att[None, None, :]).sum(axis=-1)

    return sig.tx_power_dbm - path_loss - floor_pen - wall_pen


def _walls_arrays(walls: pd.DataFrame, sig: SignalConfig):
    if walls.empty:
        return np.zeros((0, 2, 2)), np.zeros(0), np.zeros(0)
    xy = np.stack([walls[["x1", "y1"]].to_numpy(float),
                   walls[["x2", "y2"]].to_numpy(float)], axis=1)
    att = np.array([sig.wall_materials.get(str(m).lower(), 4.0) for m in walls["material"]], dtype=float)
    return xy, walls["floor"].to_numpy(float), att


@dataclass
class CoverageModel:
    """Set-cover instance: universe = targets, one set per candidate AP."""

    candidates: list[str]          # candidate AP ids (includes existing APs)
    targets: list[str]             # locations that need Wi-Fi (the universe)
    sets: dict                     # candidate -> frozenset of targets it serves (after capacity)
    in_range: dict                 # candidate -> frozenset of targets above threshold (before capacity)
    cost: dict                     # candidate -> installation cost
    existing: list[str]            # APs already installed
    rssi: np.ndarray               # (num_candidates, num_targets) signal strength in dBm


def build_coverage_model(campus: Campus, net: NetworkConfig) -> CoverageModel:
    loc = campus.locations.reset_index(drop=True)
    ids = loc["id"].tolist()
    xy = loc[["x", "y"]].to_numpy(float)
    floors = loc["floor"].to_numpy(float)
    existing_flags = loc["existing_ap"].to_numpy(bool)

    cand_idx = np.where(loc["ap_candidate"].to_numpy(bool) | existing_flags)[0]
    tgt_idx = np.where(loc["needs_coverage"].to_numpy(bool))[0]
    targets = [ids[i] for i in tgt_idx]
    candidates = [ids[i] for i in cand_idx]
    demand = loc["devices"].to_numpy(float)[tgt_idx]

    walls_xy, wall_floor, wall_att = _walls_arrays(campus.walls, net.signal)
    rssi = rssi_matrix(xy[cand_idx], floors[cand_idx], xy[tgt_idx], floors[tgt_idx],
                       walls_xy, wall_floor, wall_att, net.signal)

    threshold = net.signal.min_signal_dbm
    sets, in_range, cost = {}, {}, {}
    for r, ci in enumerate(cand_idx):
        cid = ids[ci]
        ok = np.flatnonzero(rssi[r] >= threshold)
        in_range[cid] = frozenset(targets[k] for k in ok)
        # Capacity: serve the strongest-signal locations first until the AP is full.
        order = ok[np.argsort(-rssi[r, ok], kind="stable")]
        used, served = 0.0, []
        for k in order:
            if used + demand[k] <= net.ap_capacity:
                served.append(targets[k])
                used += demand[k]
        sets[cid] = frozenset(served)
        install = loc["install_cost"].iloc[ci]
        cost[cid] = float(install) if pd.notna(install) else float(net.ap_cost)

    existing = [ids[i] for i in cand_idx if existing_flags[i]]
    return CoverageModel(candidates, targets, sets, in_range, cost, existing, rssi)


def coverage_grid(campus: Campus, net: NetworkConfig, ap_ids, floor, step: float = 1.5):
    """Best-server RSSI over a regular grid on one floor, used for the coverage heatmap."""
    loc = campus.locations
    xs = np.arange(loc["x"].min() - 5, loc["x"].max() + 5 + step, step)
    ys = np.arange(loc["y"].min() - 5, loc["y"].max() + 5 + step, step)
    X, Y = np.meshgrid(xs, ys)
    pts = np.column_stack([X.ravel(), Y.ravel()])
    if not len(ap_ids):
        return X, Y, np.full(X.shape, -120.0)
    ap_rows = loc[loc["id"].isin(ap_ids)]
    walls_xy, wall_floor, wall_att = _walls_arrays(campus.walls, net.signal)
    rssi = rssi_matrix(ap_rows[["x", "y"]].to_numpy(float), ap_rows["floor"].to_numpy(float),
                       pts, np.full(len(pts), float(floor)),
                       walls_xy, wall_floor, wall_att, net.signal)
    return X, Y, rssi.max(axis=0).reshape(X.shape)
