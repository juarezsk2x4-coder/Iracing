"""Throttle smoothness and blip-count metrics."""
from __future__ import annotations

from ..corner_detector import Corner
from ..lap_splitter import LapData


def throttle_smoothness_score(lap: LapData, corners: list[Corner]) -> float:
    """Mean of |2nd-difference| of Throttle during corner-exit phases.

    Lower is smoother. Threshold of concern: > 0.015 per sample.
    """
    throttle = lap.data.get("Throttle")
    if not throttle or len(throttle) < 3 or not corners:
        return 0.0
    rate = lap.sample_rate_hz
    total = 0.0
    count = 0
    for c in corners:
        start = c.apex_sample
        end = min(len(throttle) - 1, c.exit_sample + int(rate * 1.5))
        for i in range(start + 1, end):
            t_prev = throttle[i - 1]
            t_cur = throttle[i]
            t_next = throttle[i + 1]
            if t_prev is None or t_cur is None or t_next is None:
                continue
            jerk = abs(float(t_next) - 2.0 * float(t_cur) + float(t_prev))
            total += jerk
            count += 1
    if count == 0:
        return 0.0
    return total / count


def throttle_blip_count(lap: LapData, corners: list[Corner], threshold: float = 0.05) -> int:
    """Count throttle direction reversals (lift events) during corner exit."""
    throttle = lap.data.get("Throttle")
    if not throttle or not corners:
        return 0
    rate = lap.sample_rate_hz
    total = 0
    for c in corners:
        start = c.apex_sample
        end = min(len(throttle) - 1, c.exit_sample + int(rate * 1.5))
        prev_sign = 0
        for i in range(start + 1, end):
            t_prev = throttle[i - 1]
            t_cur = throttle[i]
            if t_prev is None or t_cur is None:
                continue
            d = float(t_cur) - float(t_prev)
            if abs(d) < threshold / rate:
                continue
            sign = 1 if d > 0 else -1
            if prev_sign != 0 and sign != prev_sign and sign < 0:
                # negative = throttle drop = blip
                total += 1
            prev_sign = sign
    return total
