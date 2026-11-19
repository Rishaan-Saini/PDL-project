"""Built-in sample campus: two academic blocks, administration, auditorium, cafeteria and grounds.

Export it to JSON with:  python -m wifi_optimizer.sample_data
Coordinates are metres on a plan view; floors stack with a height and a penalty.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

FLOOR_HEIGHT_M = 3.5
CABLE_SLACK = 1.15      # trays and bends make cable runs ~15% longer than straight lines
DEFAULT_COST = 150.0
OUTDOOR_COST = 220.0


def _loc(id_, name, type_, building, floor, x, y, devices=0, needs=False, cand=False,
         existing=False, cost=DEFAULT_COST):
    return {"id": id_, "name": name, "type": type_, "building": building, "floor": floor,
            "x": float(x), "y": float(y), "devices": devices, "needs_coverage": needs,
            "ap_candidate": cand, "existing_ap": existing, "install_cost": cost}


def _seg(floor, x1, y1, x2, y2, material):
    return {"floor": floor, "x1": float(x1), "y1": float(y1), "x2": float(x2),
            "y2": float(y2), "material": material}


def _rect(floor, x0, y0, x1, y1, material):
    return [_seg(floor, x0, y0, x1, y0, material), _seg(floor, x1, y0, x1, y1, material),
            _seg(floor, x1, y1, x0, y1, material), _seg(floor, x0, y1, x0, y0, material)]


def _cable_m(a, b):
    """Cable run = 3-D Euclidean distance x routing slack."""
    dz = (a["floor"] - b["floor"]) * FLOOR_HEIGHT_M
    d = math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + dz ** 2)
    return round(CABLE_SLACK * d, 1)


BLOCK_A, BLOCK_B = "Block A", "Block B"
ADMIN, AUDIT, CAFE, GROUNDS = "Administration", "Auditorium", "Cafeteria", "Grounds"

LOCATIONS = [
    # Block A, ground floor (x 0-60, y 0-30)
    _loc("CORR-A0", "Ground Floor Corridor", "corridor", BLOCK_A, 0, 30, 15, cand=True, existing=True),
    _loc("A-101", "Classroom A-101", "classroom", BLOCK_A, 0, 7.5, 24, 35, True),
    _loc("A-102", "Classroom A-102", "classroom", BLOCK_A, 0, 22.5, 24, 35, True),
    _loc("A-103", "Classroom A-103", "classroom", BLOCK_A, 0, 37.5, 24, 35, True, cand=True),
    _loc("A-104", "Computer Lab A-104", "lab", BLOCK_A, 0, 52.5, 24, 40, True),
    _loc("A-105", "Classroom A-105", "classroom", BLOCK_A, 0, 10, 6, 35, True),
    _loc("A-106", "Faculty Office A-106", "office", BLOCK_A, 0, 30, 6, 10, True),
    _loc("SRV", "Central Server Room", "server_room", BLOCK_A, 0, 50, 6, 0, False),
    # Block A, first floor
    _loc("CORR-A1", "First Floor Corridor", "corridor", BLOCK_A, 1, 30, 15, cand=True),
    _loc("A-201", "Classroom A-201", "classroom", BLOCK_A, 1, 7.5, 24, 35, True),
    _loc("A-202", "Classroom A-202", "classroom", BLOCK_A, 1, 22.5, 24, 35, True),
    _loc("A-203", "Classroom A-203", "classroom", BLOCK_A, 1, 37.5, 24, 35, True, cand=True),
    _loc("A-204", "Computer Lab A-204", "lab", BLOCK_A, 1, 52.5, 24, 40, True),
    _loc("A-205", "Staff Room A-205", "office", BLOCK_A, 1, 10, 6, 10, True),
    _loc("A-206", "Seminar Hall A-206", "classroom", BLOCK_A, 1, 30, 6, 30, True),
    _loc("A-207", "Classroom A-207", "classroom", BLOCK_A, 1, 50, 6, 35, True),
    # Block B (x 65-120, y 0-30)
    _loc("CORR-B0", "Ground Floor Corridor B", "corridor", BLOCK_B, 0, 92, 15, cand=True, existing=True),
    _loc("LAB-B1", "Computer Lab B-1", "lab", BLOCK_B, 0, 72.5, 24, 40, True),
    _loc("LAB-B2", "Computer Lab B-2", "lab", BLOCK_B, 0, 87.5, 24, 40, True),
    _loc("CR-B1", "Classroom B-101", "classroom", BLOCK_B, 0, 101.5, 24, 35, True),
    _loc("STUDY-B1", "Study Area B-102", "study", BLOCK_B, 0, 114, 24, 30, True),
    _loc("CR-B2", "Classroom B-103", "classroom", BLOCK_B, 0, 75, 6, 35, True),
    _loc("DEPT-B", "Department Office B-104", "office", BLOCK_B, 0, 102, 6, 10, True),
    _loc("CORR-B1", "First Floor Corridor B", "corridor", BLOCK_B, 1, 92, 15, cand=True),
    _loc("LIB", "Central Library", "library", BLOCK_B, 1, 82, 24, 80, True, cand=True),
    _loc("READ-B", "Reading Room", "study", BLOCK_B, 1, 110, 24, 30, True),
    _loc("STAFF-B", "Staff Room B-201", "office", BLOCK_B, 1, 75, 6, 10, True),
    _loc("SEM-B", "Seminar Room B-202", "classroom", BLOCK_B, 1, 102, 6, 30, True),
    # Administration block (x 0-30, y 35-60)
    _loc("CORR-ADM", "Admin Entrance Hall", "corridor", ADMIN, 0, 22.5, 38, cand=True),
    _loc("ADM-1", "Administrative Office", "office", ADMIN, 0, 7.5, 47.5, 20, True),
    _loc("RECEP", "Reception", "reception", ADMIN, 0, 22.5, 52, 15, True),
    # Auditorium (x 35-60, y 35-65) and foyer
    _loc("FOY", "Auditorium Foyer", "corridor", AUDIT, 0, 47.5, 42, cand=True),
    _loc("AUD", "Main Auditorium", "auditorium", AUDIT, 0, 47.5, 57.5, 150, True, cost=200.0),
    # Cafeteria (x 65-100, y 35-60)
    _loc("CORR-CAF", "Cafeteria Entrance", "corridor", CAFE, 0, 70, 40, cand=True),
    _loc("CAF", "Cafeteria Dining Hall", "cafeteria", CAFE, 0, 82.5, 47.5, 100, True),
    # Outdoor junctions and plaza poles (weatherproof, pricier)
    _loc("J1", "Courtyard Junction J1", "outdoor", GROUNDS, 0, 62.5, 32.5, cost=OUTDOOR_COST),
    _loc("J2", "Courtyard Junction J2", "outdoor", GROUNDS, 0, 92.5, 32.5, cost=OUTDOOR_COST),
    _loc("J3", "Plaza Pole P3", "outdoor", GROUNDS, 0, 47.5, 32.5, cand=True, cost=OUTDOOR_COST),
    _loc("J4", "Plaza Pole P4", "outdoor", GROUNDS, 0, 22.5, 32.5, cand=True, cost=OUTDOOR_COST),
]

# Hub corridor -> rooms it serves by cable (star topology per area)
ROOM_LINKS = {
    "CORR-A0": ["A-101", "A-102", "A-103", "A-104", "A-105", "A-106", "SRV"],
    "CORR-A1": ["A-201", "A-202", "A-203", "A-204", "A-205", "A-206", "A-207"],
    "CORR-B0": ["LAB-B1", "LAB-B2", "CR-B1", "STUDY-B1", "CR-B2", "DEPT-B"],
    "CORR-B1": ["LIB", "READ-B", "STAFF-B", "SEM-B"],
    "CORR-ADM": ["ADM-1", "RECEP"],
    "FOY": ["AUD"],
    "CORR-CAF": ["CAF"],
}

# Backbone links: stairwells, outdoor trenching and riser cables
TRUNK_LINKS = [
    ("CORR-A0", "CORR-A1"), ("CORR-B0", "CORR-B1"),
    ("CORR-A0", "J4"), ("CORR-A0", "J3"), ("J4", "CORR-ADM"), ("J3", "FOY"),
    ("J3", "J1"), ("J1", "J2"), ("J2", "CORR-B0"), ("J2", "CORR-CAF"),
]


def _walls():
    walls = []
    # Block A (both floors)
    for f in (0, 1):
        walls += _rect(f, 0, 0, 60, 30, "concrete")
        walls += [_seg(f, 0, 12, 60, 12, "drywall"), _seg(f, 0, 18, 60, 18, "drywall")]
        walls += [_seg(f, x, 18, x, 30, "drywall") for x in (15, 30, 45)]
        walls += [_seg(f, x, 0, x, 12, "drywall") for x in (20, 40)]
    # Block B (both floors)
    for f in (0, 1):
        walls += _rect(f, 65, 0, 120, 30, "concrete")
        walls += [_seg(f, 65, 12, 120, 12, "drywall"), _seg(f, 65, 18, 120, 18, "drywall")]
        walls += [_seg(f, x, 18, x, 30, "drywall") for x in ((80, 95, 108) if f == 0 else (100,))]
        walls += [_seg(f, 85, 0, 85, 12, "drywall")]
    # Administration, auditorium and cafeteria
    walls += _rect(0, 0, 35, 30, 60, "concrete") + [_seg(0, 15, 35, 15, 60, "glass")]
    walls += _rect(0, 35, 35, 60, 65, "concrete") + [_seg(0, 35, 50, 60, 50, "drywall")]
    walls += _rect(0, 65, 35, 100, 60, "concrete")
    return walls


def build_sample_dict() -> dict:
    by_id = {loc["id"]: loc for loc in LOCATIONS}

    def edge(a, b):
        return {"source": a, "target": b, "distance": _cable_m(by_id[a], by_id[b])}

    edges = [edge(hub, room) for hub, rooms in ROOM_LINKS.items() for room in rooms]
    edges += [edge(a, b) for a, b in TRUNK_LINKS]
    return {"name": "Sample Engineering College", "server_id": "SRV",
            "locations": LOCATIONS, "edges": edges, "walls": _walls()}


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/sample_campus.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_sample_dict(), indent=2), encoding="utf-8")
    print(f"Wrote {out}")
