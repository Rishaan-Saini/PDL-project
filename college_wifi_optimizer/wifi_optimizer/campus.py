"""Campus data model: locations, cable links and walls, plus graph construction and validation."""
from __future__ import annotations

import json
from dataclasses import dataclass

import networkx as nx
import pandas as pd

LOCATION_TYPES = ["classroom", "lab", "library", "office", "reception", "study",
                  "auditorium", "cafeteria", "corridor", "server_room", "outdoor"]
LOCATION_COLUMNS = ["id", "name", "type", "building", "floor", "x", "y", "devices",
                    "needs_coverage", "ap_candidate", "existing_ap", "install_cost"]
EDGE_COLUMNS = ["source", "target", "distance"]
WALL_COLUMNS = ["floor", "x1", "y1", "x2", "y2", "material"]
_NUMERIC_LOC = ["floor", "x", "y", "devices", "install_cost"]
_BOOL_LOC = ["needs_coverage", "ap_candidate", "existing_ap"]


def _text(series: pd.Series) -> pd.Series:
    return series.apply(lambda v: "" if pd.isna(v) else str(v).strip())


@dataclass
class Campus:
    """A campus layout. Tables are pandas DataFrames so they can be edited in Streamlit."""

    name: str
    locations: pd.DataFrame
    edges: pd.DataFrame
    walls: pd.DataFrame
    server_id: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Campus":
        loc = pd.DataFrame(data.get("locations") or [], columns=LOCATION_COLUMNS).copy()
        for col in _NUMERIC_LOC:
            loc[col] = pd.to_numeric(loc[col], errors="coerce")
        for col in _BOOL_LOC:
            loc[col] = loc[col].fillna(False).astype(bool)
        for col in ["id", "name", "type", "building"]:
            loc[col] = _text(loc[col])

        edges = pd.DataFrame(data.get("edges") or [], columns=EDGE_COLUMNS).copy()
        edges["distance"] = pd.to_numeric(edges["distance"], errors="coerce")
        edges["source"] = _text(edges["source"])
        edges["target"] = _text(edges["target"])

        walls = pd.DataFrame(data.get("walls") or [], columns=WALL_COLUMNS).copy()
        for col in ["floor", "x1", "y1", "x2", "y2"]:
            walls[col] = pd.to_numeric(walls[col], errors="coerce")
        walls["material"] = _text(walls["material"]).str.lower()

        return cls(
            name=str(data.get("name") or "Campus"),
            locations=loc.reset_index(drop=True),
            edges=edges.reset_index(drop=True),
            walls=walls.reset_index(drop=True),
            server_id=str(data.get("server_id") or "").strip(),
        )

    def to_dict(self) -> dict:
        def records(df: pd.DataFrame) -> list:
            return df.astype(object).where(df.notna(), None).to_dict("records")

        return {"name": self.name, "server_id": self.server_id,
                "locations": records(self.locations), "edges": records(self.edges),
                "walls": records(self.walls)}

    def normalised(self) -> "Campus":
        """Return a cleaned copy (fixes NaN rows added in the table editor)."""
        return Campus.from_dict(self.to_dict())


def empty_campus(name: str = "New Campus") -> Campus:
    return Campus(name, pd.DataFrame(columns=LOCATION_COLUMNS),
                  pd.DataFrame(columns=EDGE_COLUMNS), pd.DataFrame(columns=WALL_COLUMNS), "")


def sample_campus() -> Campus:
    from .sample_data import build_sample_dict
    return Campus.from_dict(build_sample_dict())


def campus_from_json_text(text: str) -> Campus:
    return Campus.from_dict(json.loads(text))


def candidate_ids(campus: Campus) -> list[str]:
    loc = campus.locations
    mask = loc["ap_candidate"] | loc["existing_ap"]
    return loc.loc[mask, "id"].tolist()


def build_graph(campus: Campus) -> nx.Graph:
    """Weighted campus graph: nodes are locations, edge weight 'distance' is the cable run in metres."""
    G = nx.Graph(name=campus.name)
    for rec in campus.locations.to_dict("records"):
        G.add_node(
            rec["id"], name=rec["name"], type=rec["type"], building=rec["building"],
            floor=float(rec["floor"]), pos=(float(rec["x"]), float(rec["y"])),
            devices=float(rec["devices"]), needs_coverage=bool(rec["needs_coverage"]),
            ap_candidate=bool(rec["ap_candidate"]), existing_ap=bool(rec["existing_ap"]),
        )
    for rec in campus.edges.to_dict("records"):
        G.add_edge(rec["source"], rec["target"], distance=float(rec["distance"]))
    return G


def validate_campus(campus: Campus) -> list[str]:
    """Return a list of human-readable problems; an empty list means the campus is usable."""
    errors: list[str] = []
    loc = campus.locations
    if loc.empty:
        return ["The campus has no locations yet."]

    ids = loc["id"].tolist()
    if "" in ids:
        errors.append("Every location needs an ID.")
    dupes = sorted({i for i in ids if i and ids.count(i) > 1})
    if dupes:
        errors.append("Duplicate location IDs: " + ", ".join(dupes) + ".")
    for col in ["floor", "x", "y", "devices"]:
        if loc[col].isna().any():
            errors.append(f"Column '{col}' must contain a number in every row.")
    if (loc["devices"] < 0).any():
        errors.append("Device demand cannot be negative.")
    if (loc["install_cost"] < 0).any():
        errors.append("AP installation cost cannot be negative.")

    id_set = set(ids)
    if campus.server_id not in id_set:
        errors.append("Choose a central server room that exists in the location list.")
    if not loc["needs_coverage"].any():
        errors.append("Mark at least one location as needing Wi-Fi.")
    if not candidate_ids(campus):
        errors.append("Mark at least one location as an AP candidate.")

    if campus.edges.empty:
        errors.append("Add connections between locations so cables can be routed.")
    else:
        e = campus.edges
        unknown = sorted({v for v in pd.concat([e["source"], e["target"]]) if v not in id_set})
        if unknown:
            errors.append("Connections refer to unknown IDs: " + ", ".join(unknown) + ".")
        if e["distance"].isna().any() or (e["distance"] <= 0).any():
            errors.append("Every connection needs a positive distance.")

    if campus.walls[["floor", "x1", "y1", "x2", "y2"]].isna().any().any():
        errors.append("Walls need numeric floor and coordinate values.")

    if not errors:
        G = build_graph(campus)
        unreachable = [c for c in candidate_ids(campus)
                       if not nx.has_path(G, campus.server_id, c)]
        if unreachable:
            errors.append("No cable route from the server room to: " + ", ".join(unreachable) + ".")
    return errors
