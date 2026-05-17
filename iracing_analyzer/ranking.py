"""Rank diagnosed weaknesses by estimated lap-time cost."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .metrics.registry import MetricsResult


class RootCause(Enum):
    HARDWARE = "hardware-limited"
    SETTINGS = "settings-limited"
    TECHNIQUE = "technique-limited"
    AMBIGUOUS = "ambiguous"


@dataclass
class Weakness:
    key: str
    name: str
    metric_value: float | str
    metric_unit: str
    lap_time_cost_s: float
    cost_math: str
    channels_used: list[str]
    inference_flag: str | None
    root_cause: RootCause = RootCause.AMBIGUOUS
    root_cause_justification: str = ""
    corner_ids: list[int] = field(default_factory=list)


# --- cost heuristics -----------------------------------------------------------

def _trail_brake_cost(pct: float, n_corners: int) -> tuple[float, str]:
    # Reference: ~5% of lap spent trail-braking is a coaching benchmark
    target = 5.0
    deficit = max(0.0, target - pct)
    cost = 0.01 * deficit * max(n_corners, 1)
    math = f"deficit={deficit:.2f}% × 0.01s × {n_corners} corners [HEURISTIC]"
    return cost, math


def _brake_cv_cost(cv: float, n_corners: int) -> tuple[float, str]:
    # Each 0.01 CV ≈ 0.005s per zone, only counted above 0.07 noise floor
    excess = max(0.0, cv - 0.07)
    cost = excess * 0.25 * max(n_corners, 1)
    math = f"(CV={cv:.3f} - 0.07) × 0.25 × {n_corners} corners [HEURISTIC]"
    return cost, math


def _steering_jitter_cost(rms: float, n_corners: int) -> tuple[float, str]:
    excess = max(0.0, rms - 0.015)
    cost = excess * 0.4 * max(n_corners, 1)
    math = f"(jitter_rms={rms:.4f} - 0.015) × 0.4 × {n_corners} corners [HEURISTIC]"
    return cost, math


def _throttle_blip_cost(blips: float, n_laps: int) -> tuple[float, str]:
    cost = 0.008 * blips
    math = f"0.008s × {blips:.1f} blips/lap [HEURISTIC]"
    return cost, math


def _throttle_smoothness_cost(score: float, n_corners: int) -> tuple[float, str]:
    excess = max(0.0, score - 0.015)
    cost = excess * 2.0 * max(n_corners, 1)
    math = f"(jerk={score:.4f} - 0.015) × 2.0 × {n_corners} corners [HEURISTIC]"
    return cost, math


def _speed_delta_cost(cost_s: float) -> tuple[float, str]:
    math = f"sum(-Δv × d / v²) across matched corners [PHYSICS-BASED]"
    return cost_s, math


def _brake_rate_cost(rate: float, n_corners: int) -> tuple[float, str]:
    # ideal range 15-40 %/100ms. Outside range = cost.
    if rate < 15.0:
        deficit = 15.0 - rate
        cost = 0.012 * deficit * max(n_corners, 1) / 10
        math = f"slow brake onset: ({15.0 - rate:.1f}% deficit) × 0.0012s × {n_corners} corners [HEURISTIC]"
        return cost, math
    if rate > 50.0:
        excess = rate - 50.0
        cost = 0.008 * excess * max(n_corners, 1) / 10
        math = f"too-rapid brake (locking risk): ({rate - 50.0:.1f}% excess) × 0.0008s × {n_corners} corners [HEURISTIC]"
        return cost, math
    return 0.0, "rate within 15-40 %/100ms target band"


# --- ranking -------------------------------------------------------------------

def rank_weaknesses(result: MetricsResult) -> list[Weakness]:
    if not result.lap_metrics or result.reference_lap is None:
        return []

    ref_corner_count = max(
        (len(m.corners) for m in result.lap_metrics), default=0
    ) or 1

    weaknesses: list[Weakness] = []
    agg = result.aggregate

    # 1. Corner speed cost (physics-based; usually the largest single number)
    speed_cost = agg.get("mean_speed_cost_s", 0.0)
    if speed_cost > 0.05:
        # find worst 3 corners
        worst_corners: dict[int, float] = {}
        for lm in result.lap_metrics:
            if lm.lap is result.reference_lap:
                continue
            for d in lm.speed_deltas:
                worst_corners[d.corner_id] = (
                    worst_corners.get(d.corner_id, 0.0) + d.lap_time_cost_s
                )
        top = sorted(worst_corners.items(), key=lambda kv: kv[1], reverse=True)[:3]
        corner_ids = [cid for cid, _ in top]
        cost, math = _speed_delta_cost(speed_cost)
        weaknesses.append(Weakness(
            key="mid_corner_speed",
            name="Mid-corner minimum speed deficit vs. reference lap",
            metric_value=speed_cost,
            metric_unit="seconds/lap",
            lap_time_cost_s=cost,
            cost_math=math,
            channels_used=["Speed", "LapDist"],
            inference_flag=None,
            corner_ids=corner_ids,
        ))

    # 2. Trail-braking deficit
    trail = agg.get("mean_trail_brake_pct")
    if trail is not None and trail < 5.0:
        cost, math = _trail_brake_cost(trail, ref_corner_count)
        if cost > 0.01:
            weaknesses.append(Weakness(
                key="trail_braking",
                name="Insufficient trail-braking",
                metric_value=trail,
                metric_unit="% of lap",
                lap_time_cost_s=cost,
                cost_math=math,
                channels_used=["Brake", "SteeringWheelAngle"],
                inference_flag=None,
            ))
    elif trail is None:
        weaknesses.append(Weakness(
            key="trail_braking",
            name="Trail-braking duration (unmeasured)",
            metric_value="n/a",
            metric_unit="",
            lap_time_cost_s=0.0,
            cost_math="SteeringWheelAngle channel unavailable",
            channels_used=["Brake"],
            inference_flag="SteeringWheelAngle missing — trail-braking overlap not measurable",
        ))

    # 3. Brake pressure CV
    if result.brake_cv_by_corner:
        worst_cv = max(result.brake_cv_by_corner.items(), key=lambda kv: kv[1])
        cid, cv = worst_cv
        all_cvs = list(result.brake_cv_by_corner.values())
        mean_cv = sum(all_cvs) / len(all_cvs)
        cost, math = _brake_cv_cost(mean_cv, ref_corner_count)
        if cost > 0.01:
            weaknesses.append(Weakness(
                key="brake_cv",
                name="Inconsistent peak brake pressure across laps",
                metric_value=mean_cv,
                metric_unit="coefficient of variation",
                lap_time_cost_s=cost,
                cost_math=math + f" (worst: T{cid} CV={cv:.3f})",
                channels_used=["Brake"],
                inference_flag=None,
                corner_ids=[cid],
            ))

    # 4. Steering jitter
    jitter = agg.get("mean_steering_jitter_rms")
    if jitter is not None:
        cost, math = _steering_jitter_cost(jitter, ref_corner_count)
        if cost > 0.01:
            weaknesses.append(Weakness(
                key="steering_jitter",
                name="Steering input jitter inside corners",
                metric_value=jitter,
                metric_unit="rad RMS",
                lap_time_cost_s=cost,
                cost_math=math,
                channels_used=["SteeringWheelAngle"],
                inference_flag=None,
            ))

    # 5. Throttle blips
    blips = agg.get("mean_throttle_blips", 0.0)
    if blips > 1.5:
        cost, math = _throttle_blip_cost(blips, len(result.lap_metrics))
        weaknesses.append(Weakness(
            key="throttle_blips",
            name="Throttle hesitation / lift events at corner exit",
            metric_value=blips,
            metric_unit="blips/lap",
            lap_time_cost_s=cost,
            cost_math=math,
            channels_used=["Throttle"],
            inference_flag=None,
        ))

    # 6. Throttle smoothness
    sm = agg.get("mean_throttle_smoothness", 0.0)
    if sm > 0.015:
        cost, math = _throttle_smoothness_cost(sm, ref_corner_count)
        if cost > 0.01:
            weaknesses.append(Weakness(
                key="throttle_smoothness",
                name="Coarse throttle application (high jerk)",
                metric_value=sm,
                metric_unit="jerk score",
                lap_time_cost_s=cost,
                cost_math=math,
                channels_used=["Throttle"],
                inference_flag=None,
            ))

    # 7. Brake application rate
    brake_rate = agg.get("mean_brake_rate", 0.0)
    if brake_rate > 0:
        cost, math = _brake_rate_cost(brake_rate, ref_corner_count)
        if cost > 0.01:
            weaknesses.append(Weakness(
                key="brake_rate",
                name="Brake application rate outside ideal band",
                metric_value=brake_rate,
                metric_unit="%/100ms",
                lap_time_cost_s=cost,
                cost_math=math,
                channels_used=["Brake"],
                inference_flag=None,
            ))

    weaknesses.sort(key=lambda w: w.lap_time_cost_s, reverse=True)
    return weaknesses
