"""Steering input jitter and over-correction metrics."""
from __future__ import annotations

import math
from statistics import mean

from ..corner_detector import Corner
from ..lap_splitter import LapData


def _rolling_mean(data: list[float], window: int = 11) -> list[float]:
    half = window // 2
    out = list(data)
    for i in range(half, len(data) - half):
        s = 0.0
        for j in range(i - half, i + half + 1):
            s += data[j]
        out[i] = s / window
    return out


def steering_jitter_rms(lap: LapData, corners: list[Corner]) -> float | None:
    """RMS of high-pass filtered SteeringWheelAngle within corners.

    Returns None if the channel is missing.
    """
    steering = lap.data.get("SteeringWheelAngle")
    if not steering:
        return None
    floats = [float(v) if v is not None else 0.0 for v in steering]
    smoothed = _rolling_mean(floats, window=11)
    samples_in_corner: list[float] = []
    for c in corners:
        for i in range(c.entry_sample, c.exit_sample + 1):
            if i >= len(floats):
                break
            samples_in_corner.append(floats[i] - smoothed[i])
    if not samples_in_corner:
        return 0.0
    sq_sum = sum(v * v for v in samples_in_corner)
    return math.sqrt(sq_sum / len(samples_in_corner))


def over_correction_count(lap: LapData, corners: list[Corner]) -> int:
    """Count steering reversals exceeding 0.03 rad in <3 samples within corners."""
    steering = lap.data.get("SteeringWheelAngle")
    if not steering:
        return 0
    total = 0
    for c in corners:
        last_sample = min(c.exit_sample + 1, len(steering))
        for i in range(c.entry_sample + 2, last_sample):
            if steering[i] is None or steering[i - 2] is None:
                continue
            d = float(steering[i]) - float(steering[i - 2])
            if abs(d) > 0.03:
                # check if direction changed in this 3-sample window
                d1 = float(steering[i - 1] or 0) - float(steering[i - 2] or 0)
                d2 = float(steering[i] or 0) - float(steering[i - 1] or 0)
                if d1 * d2 < 0:
                    total += 1
    return total
