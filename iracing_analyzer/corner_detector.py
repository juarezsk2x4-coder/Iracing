"""Speed-minima corner detection. Pure stdlib (no numpy)."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from .lap_splitter import LapData


@dataclass
class Corner:
    corner_id: int
    entry_sample: int
    apex_sample: int
    exit_sample: int
    lap_dist_entry: float | None
    lap_dist_apex: float | None
    lap_dist_exit: float | None
    min_speed_mps: float
    entry_speed_mps: float
    corner_type: str


def _rolling_mean(data: list[float], window: int) -> list[float]:
    if window <= 1 or len(data) <= window:
        return list(data)
    half = window // 2
    out = list(data)
    for i in range(half, len(data) - half):
        out[i] = mean(data[i - half : i + half + 1])
    return out


def _safe_min(data: list[float]) -> float:
    return min(v for v in data if v is not None) if data else float("inf")


def detect_corners(
    lap: LapData,
    min_speed_drop_pct: float = 0.08,
    min_duration_samples: int = 6,
    apex_window: int = 15,
    lat_accel_threshold: float = 2.94,  # m/s^2 = 0.3g
) -> list[Corner]:
    """Detect corners as qualified local minima in the Speed channel."""
    speed = lap.data.get("Speed")
    if not speed or len(speed) < apex_window * 2 + 1:
        return []
    smoothed = _rolling_mean([float(v) for v in speed], window=5)
    lat = lap.data.get("LateralAccel")
    lap_dist = lap.data.get("LapDist")

    n = len(smoothed)
    candidates: list[int] = []
    for i in range(apex_window, n - apex_window):
        left = smoothed[i - apex_window : i]
        right = smoothed[i + 1 : i + apex_window + 1]
        if not left or not right:
            continue
        if smoothed[i] < min(left) and smoothed[i] < min(right):
            candidates.append(i)

    corners: list[Corner] = []
    used_ranges: list[tuple[int, int]] = []

    for apex in candidates:
        # find pre-corner max within a look-back window
        lookback = max(0, apex - apex_window * 3)
        pre_max = max(smoothed[lookback:apex]) if apex > lookback else smoothed[apex]
        if pre_max <= 0:
            continue
        drop = (pre_max - smoothed[apex]) / pre_max
        if drop < min_speed_drop_pct:
            continue

        # entry: scan back to where speed > apex_speed * 1.08
        entry = apex
        threshold = smoothed[apex] * 1.08
        for j in range(apex - 1, max(-1, apex - apex_window * 4), -1):
            if smoothed[j] >= threshold:
                entry = j
                break
        # exit: scan forward to recovery
        exit_s = apex
        for j in range(apex + 1, min(n, apex + apex_window * 4)):
            if smoothed[j] >= threshold:
                exit_s = j
                break

        if exit_s - entry < min_duration_samples:
            continue

        if lat:
            lat_val = lat[apex] if apex < len(lat) and lat[apex] is not None else 0.0
            if abs(float(lat_val)) < lat_accel_threshold:
                continue

        # deduplicate overlapping corners (keep deepest)
        overlap = False
        for (s, e) in used_ranges:
            if not (exit_s < s or entry > e):
                overlap = True
                break
        if overlap:
            continue
        used_ranges.append((entry, exit_s))

        def _ld(idx: int) -> float | None:
            if lap_dist and idx < len(lap_dist) and lap_dist[idx] is not None:
                return float(lap_dist[idx])
            return None

        ctype = _classify_corner_type(smoothed, entry, apex, exit_s)
        corners.append(
            Corner(
                corner_id=0,
                entry_sample=entry,
                apex_sample=apex,
                exit_sample=exit_s,
                lap_dist_entry=_ld(entry),
                lap_dist_apex=_ld(apex),
                lap_dist_exit=_ld(exit_s),
                min_speed_mps=float(smoothed[apex]),
                entry_speed_mps=float(smoothed[entry]),
                corner_type=ctype,
            )
        )

    corners.sort(key=lambda c: c.entry_sample)
    for idx, c in enumerate(corners):
        c.corner_id = idx + 1
    return corners


def _classify_corner_type(speed: list[float], entry: int, apex: int, exit_s: int) -> str:
    """Classify corner shape from the speed profile."""
    if exit_s <= entry:
        return "unknown"
    drop_ratio = (speed[entry] - speed[apex]) / max(speed[entry], 0.001)
    if drop_ratio > 0.55:
        return "hairpin"
    if drop_ratio > 0.20:
        return "braking"
    return "constant_radius"


def match_corners_across_laps(
    ref: list[Corner],
    other: list[Corner],
    lap_dist_tolerance_m: float = 50.0,
    sample_tolerance: int = 90,
) -> list[tuple[Corner, Corner]]:
    """Pair corners between two laps by LapDist (preferred) or sample index."""
    pairs: list[tuple[Corner, Corner]] = []
    used: set[int] = set()
    use_lap_dist = (
        all(c.lap_dist_apex is not None for c in ref)
        and all(c.lap_dist_apex is not None for c in other)
    )
    for rc in ref:
        best_idx = -1
        best_dist = float("inf")
        for j, oc in enumerate(other):
            if j in used:
                continue
            if use_lap_dist:
                d = abs(rc.lap_dist_apex - oc.lap_dist_apex)
                tol = lap_dist_tolerance_m
            else:
                d = abs(rc.apex_sample - oc.apex_sample)
                tol = sample_tolerance
            if d < tol and d < best_dist:
                best_dist = d
                best_idx = j
        if best_idx >= 0:
            used.add(best_idx)
            pairs.append((rc, other[best_idx]))
    return pairs
