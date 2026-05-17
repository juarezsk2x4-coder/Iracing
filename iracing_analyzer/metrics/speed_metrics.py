"""Mid-corner minimum-speed deltas vs. reference lap."""
from __future__ import annotations

from dataclasses import dataclass

from ..corner_detector import Corner


@dataclass
class SpeedDelta:
    corner_id: int
    ref_min_speed_mps: float
    lap_min_speed_mps: float
    delta_mps: float
    corner_length_m: float | None
    lap_time_cost_s: float


def corner_speed_deltas(
    matched_pairs: list[tuple[Corner, Corner]],
) -> list[SpeedDelta]:
    """Compute min-speed delta per matched (ref, lap) corner pair.

    Lap-time cost uses first-order kinematics: dT ≈ -Δv × d / v².
    Length is estimated from LapDist entry→exit when available.
    """
    out: list[SpeedDelta] = []
    for ref, lap in matched_pairs:
        delta = lap.min_speed_mps - ref.min_speed_mps
        length: float | None = None
        if ref.lap_dist_entry is not None and ref.lap_dist_exit is not None:
            length = abs(ref.lap_dist_exit - ref.lap_dist_entry)
        cost = 0.0
        if length and ref.min_speed_mps > 1.0 and delta < 0:
            cost = -delta * length / (ref.min_speed_mps ** 2)
        out.append(
            SpeedDelta(
                corner_id=ref.corner_id,
                ref_min_speed_mps=ref.min_speed_mps,
                lap_min_speed_mps=lap.min_speed_mps,
                delta_mps=delta,
                corner_length_m=length,
                lap_time_cost_s=cost,
            )
        )
    return out


def total_speed_cost(deltas: list[SpeedDelta]) -> float:
    return sum(d.lap_time_cost_s for d in deltas)
