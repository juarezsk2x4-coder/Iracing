"""Brake-channel metrics: application rate, peak pressure consistency, trail-braking."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev

from ..corner_detector import Corner
from ..lap_splitter import LapData


BRAKE_THRESHOLD = 0.02
STEER_THRESHOLD_RAD = 0.05


@dataclass
class BrakeZone:
    corner_id: int
    onset_sample: int
    peak_sample: int
    release_sample: int
    peak_pressure: float
    application_rate_pct_per_100ms: float
    trail_brake_duration_s: float | None
    trail_brake_inferred: bool  # True if SteeringWheelAngle missing


def extract_brake_zones(lap: LapData, corners: list[Corner]) -> list[BrakeZone]:
    """For each corner, find the brake zone preceding the apex."""
    brake = lap.data.get("Brake")
    if not brake:
        return []
    rate = lap.sample_rate_hz
    steering = lap.data.get("SteeringWheelAngle")
    zones: list[BrakeZone] = []
    lookback = int(rate * 3.0)  # 3-second look-back

    for c in corners:
        scan_start = max(0, c.entry_sample - lookback)
        scan_end = c.apex_sample
        if scan_end <= scan_start:
            continue
        window = brake[scan_start:scan_end]
        # onset: first index where Brake > threshold
        onset_rel = next(
            (i for i, v in enumerate(window) if v is not None and float(v) > BRAKE_THRESHOLD),
            None,
        )
        if onset_rel is None:
            continue
        onset = scan_start + onset_rel
        # peak within [onset, apex + some)
        peak_end = min(len(brake), c.apex_sample + int(rate * 0.5))
        peak_window = brake[onset:peak_end]
        if not peak_window:
            continue
        peak_val = max(float(v) for v in peak_window if v is not None)
        peak = onset + next(
            i for i, v in enumerate(peak_window) if v is not None and float(v) >= peak_val
        )
        # release: last index where Brake > threshold within zone
        rel_window = brake[onset:peak_end]
        rel_rel = max(
            (i for i, v in enumerate(rel_window) if v is not None and float(v) > BRAKE_THRESHOLD),
            default=0,
        )
        release = onset + rel_rel

        # application rate: peak rise from onset to peak
        rise_time_s = (peak - onset) / rate
        if rise_time_s <= 0:
            rate_pct = 0.0
        else:
            rise = (peak_val - float(brake[onset] or 0.0)) * 100.0
            rate_pct = rise / (rise_time_s * 10.0)  # % per 100ms

        # trail-braking overlap
        trail_dur: float | None = None
        inferred = False
        if steering:
            overlap = 0
            for i in range(onset, release + 1):
                if i >= len(steering) or i >= len(brake):
                    break
                b = brake[i]
                s = steering[i]
                if b is None or s is None:
                    continue
                if float(b) > BRAKE_THRESHOLD and abs(float(s)) > STEER_THRESHOLD_RAD:
                    overlap += 1
            trail_dur = overlap / rate
        else:
            trail_dur = None
            inferred = True

        zones.append(
            BrakeZone(
                corner_id=c.corner_id,
                onset_sample=onset,
                peak_sample=peak,
                release_sample=release,
                peak_pressure=peak_val,
                application_rate_pct_per_100ms=rate_pct,
                trail_brake_duration_s=trail_dur,
                trail_brake_inferred=inferred,
            )
        )
    return zones


def peak_pressure_cv(zones_by_lap: list[list[BrakeZone]]) -> dict[int, float]:
    """Compute coefficient of variation of peak pressure per corner across laps."""
    by_corner: dict[int, list[float]] = {}
    for laps_zones in zones_by_lap:
        for z in laps_zones:
            by_corner.setdefault(z.corner_id, []).append(z.peak_pressure)
    out: dict[int, float] = {}
    for cid, vals in by_corner.items():
        if len(vals) < 2:
            continue
        m = mean(vals)
        if m <= 0:
            continue
        out[cid] = pstdev(vals) / m
    return out


def mean_application_rate(zones: list[BrakeZone]) -> float:
    if not zones:
        return 0.0
    return mean(z.application_rate_pct_per_100ms for z in zones)


def mean_trail_brake_pct(zones: list[BrakeZone], lap_duration_s: float) -> float | None:
    """Trail-braking time as a percentage of lap duration. None if not measurable."""
    measurable = [z for z in zones if z.trail_brake_duration_s is not None]
    if not measurable or lap_duration_s <= 0:
        return None
    total = sum(z.trail_brake_duration_s for z in measurable)
    return 100.0 * total / lap_duration_s
