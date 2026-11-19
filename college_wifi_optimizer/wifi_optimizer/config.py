"""Tunable parameters for the signal model, AP hardware and the optimiser."""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_WALL_MATERIALS = {"drywall": 4.0, "glass": 3.0, "brick": 8.0, "concrete": 12.0}


@dataclass
class SignalConfig:
    """Log-distance path-loss model with wall and floor penalties.

    RSSI(d) = P_tx - [PL(d0) + 10 * n * log10(d / d0)] - floor_loss * |floor diff| - sum(wall_loss)

    This is a planning approximation, not a substitute for a professional RF site survey.
    """

    tx_power_dbm: float = 20.0
    ref_loss_db: float = 40.0          # path loss at reference distance d0 (typical for 2.4 GHz)
    ref_distance_m: float = 1.0        # d0
    path_loss_exponent: float = 3.0    # n: ~2 open space, 3-4 cluttered indoor
    min_signal_dbm: float = -70.0      # minimum acceptable signal for a location to count as covered
    floor_height_m: float = 3.5
    floor_loss_db: float = 15.0        # penalty per floor crossed
    wall_materials: dict = field(default_factory=lambda: dict(DEFAULT_WALL_MATERIALS))

    def coverage_radius_m(self) -> float:
        """Distance at which RSSI reaches the threshold in obstacle-free space."""
        margin = self.tx_power_dbm - self.ref_loss_db - self.min_signal_dbm
        return self.ref_distance_m * 10 ** (margin / (10.0 * self.path_loss_exponent))


@dataclass
class NetworkConfig:
    """AP hardware, cabling and optimisation settings."""

    ap_cost: float = 150.0             # default installation cost per AP
    ap_capacity: int = 300             # maximum device demand one AP can serve (strongest signals served first)
    cable_cost_per_m: float = 2.5
    target_coverage: float = 0.95      # fraction of Wi-Fi locations that must be covered
    budget: float = 2500.0             # used by Maximum Coverage mode
    keep_existing_aps: bool = True
    signal: SignalConfig = field(default_factory=SignalConfig)

    def validate(self) -> list[str]:
        errors = []
        if not 0 < self.target_coverage <= 1:
            errors.append("Target coverage must be between 0% and 100%.")
        if self.ap_cost < 0 or self.cable_cost_per_m < 0 or self.budget < 0:
            errors.append("Costs and budget cannot be negative.")
        if self.ap_capacity <= 0:
            errors.append("AP capacity must be positive.")
        s = self.signal
        if s.path_loss_exponent <= 0 or s.ref_distance_m <= 0 or s.floor_height_m <= 0:
            errors.append("Path-loss exponent, reference distance and floor height must be positive.")
        if any(v < 0 for v in s.wall_materials.values()):
            errors.append("Wall attenuation values cannot be negative.")
        return errors
