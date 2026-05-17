"""Run all metrics for a session and produce a unified MetricsResult."""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean

from ..corner_detector import Corner, detect_corners, match_corners_across_laps
from ..ibt_parser import ParsedSession
from ..lap_splitter import LapData, find_reference_lap, split_laps
from .brake_metrics import (
    BrakeZone,
    extract_brake_zones,
    mean_application_rate,
    mean_trail_brake_pct,
    peak_pressure_cv,
)
from .speed_metrics import SpeedDelta, corner_speed_deltas, total_speed_cost
from .steering_metrics import over_correction_count, steering_jitter_rms
from .throttle_metrics import throttle_blip_count, throttle_smoothness_score


@dataclass
class LapMetrics:
    lap: LapData
    corners: list[Corner]
    brake_zones: list[BrakeZone]
    mean_brake_rate: float
    mean_trail_brake_pct: float | None
    throttle_smoothness: float
    throttle_blips: int
    steering_jitter_rms: float | None
    over_corrections: int
    speed_deltas: list[SpeedDelta]
    total_speed_cost_s: float


@dataclass
class MetricsResult:
    session: ParsedSession
    laps: list[LapData]
    reference_lap: LapData | None
    lap_metrics: list[LapMetrics]
    brake_cv_by_corner: dict[int, float]
    aggregate: dict[str, float] = field(default_factory=dict)


def compute_metrics(session: ParsedSession) -> MetricsResult:
    laps = split_laps(session)
    valid_laps = [l for l in laps if l.is_valid]
    ref = find_reference_lap(valid_laps)

    lap_metrics: list[LapMetrics] = []
    ref_corners: list[Corner] = []
    if ref is not None:
        ref_corners = detect_corners(ref)

    all_brake_zones_by_lap: list[list[BrakeZone]] = []

    for lap in valid_laps:
        corners = detect_corners(lap)
        # renumber corners to match reference numbering when possible
        if ref_corners and corners and lap is not ref:
            pairs = match_corners_across_laps(ref_corners, corners)
            id_map = {oc.apex_sample: rc.corner_id for rc, oc in pairs}
            for c in corners:
                c.corner_id = id_map.get(c.apex_sample, c.corner_id)

        zones = extract_brake_zones(lap, corners)
        all_brake_zones_by_lap.append(zones)

        mean_rate = mean_application_rate(zones)
        trail_pct = mean_trail_brake_pct(zones, lap.lap_time_s or lap.duration_s)
        throttle_sm = throttle_smoothness_score(lap, corners)
        blips = throttle_blip_count(lap, corners)
        jitter = steering_jitter_rms(lap, corners)
        over_corr = over_correction_count(lap, corners)

        if lap is ref:
            deltas: list[SpeedDelta] = []
            cost_total = 0.0
        else:
            pairs = match_corners_across_laps(ref_corners, corners) if ref_corners else []
            deltas = corner_speed_deltas(pairs)
            cost_total = total_speed_cost(deltas)

        lap_metrics.append(
            LapMetrics(
                lap=lap,
                corners=corners,
                brake_zones=zones,
                mean_brake_rate=mean_rate,
                mean_trail_brake_pct=trail_pct,
                throttle_smoothness=throttle_sm,
                throttle_blips=blips,
                steering_jitter_rms=jitter,
                over_corrections=over_corr,
                speed_deltas=deltas,
                total_speed_cost_s=cost_total,
            )
        )

    cv_by_corner = peak_pressure_cv(all_brake_zones_by_lap)

    aggregate: dict[str, float] = {}
    if lap_metrics:
        aggregate["mean_brake_rate"] = mean(m.mean_brake_rate for m in lap_metrics)
        trail_vals = [m.mean_trail_brake_pct for m in lap_metrics if m.mean_trail_brake_pct is not None]
        if trail_vals:
            aggregate["mean_trail_brake_pct"] = mean(trail_vals)
        aggregate["mean_throttle_smoothness"] = mean(m.throttle_smoothness for m in lap_metrics)
        aggregate["mean_throttle_blips"] = mean(m.throttle_blips for m in lap_metrics)
        jitter_vals = [m.steering_jitter_rms for m in lap_metrics if m.steering_jitter_rms is not None]
        if jitter_vals:
            aggregate["mean_steering_jitter_rms"] = mean(jitter_vals)
        aggregate["mean_over_corrections"] = mean(m.over_corrections for m in lap_metrics)
        non_ref = [m for m in lap_metrics if m.lap is not ref]
        if non_ref:
            aggregate["mean_speed_cost_s"] = mean(m.total_speed_cost_s for m in non_ref)

    return MetricsResult(
        session=session,
        laps=valid_laps,
        reference_lap=ref,
        lap_metrics=lap_metrics,
        brake_cv_by_corner=cv_by_corner,
        aggregate=aggregate,
    )
