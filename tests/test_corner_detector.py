"""Unit tests for corner detection using synthetic speed traces."""
import math

from iracing_analyzer.corner_detector import detect_corners, match_corners_across_laps
from iracing_analyzer.lap_splitter import LapData


def _synthetic_lap(corner_count: int = 3, rate: float = 60.0) -> LapData:
    """Build a lap with `corner_count` evenly spaced speed minima."""
    samples_per_corner = 300
    total = samples_per_corner * corner_count
    speed: list[float] = []
    lat: list[float] = []
    for i in range(total):
        within = i % samples_per_corner
        # cosine-shaped speed valley
        s = 60.0 - 35.0 * (1 - math.cos(2 * math.pi * within / samples_per_corner)) / 2
        speed.append(s)
        # synthetic lateral accel — peaks (in magnitude) at apex
        l = -10.0 * (1 - math.cos(2 * math.pi * within / samples_per_corner)) / 2
        lat.append(l)
    return LapData(
        lap_number=1,
        start_sample=0,
        end_sample=total,
        lap_time_s=total / rate,
        is_valid=True,
        data={"Speed": speed, "LateralAccel": lat, "LapDist": list(range(total))},
        sample_rate_hz=rate,
    )


def test_detects_correct_number_of_corners():
    lap = _synthetic_lap(corner_count=3)
    corners = detect_corners(lap)
    assert len(corners) == 3, f"expected 3 corners, got {len(corners)}"


def test_corners_have_increasing_apex_samples():
    lap = _synthetic_lap(corner_count=4)
    corners = detect_corners(lap)
    apexes = [c.apex_sample for c in corners]
    assert apexes == sorted(apexes)


def test_corner_id_starts_at_1():
    lap = _synthetic_lap(corner_count=2)
    corners = detect_corners(lap)
    assert corners[0].corner_id == 1
    assert corners[1].corner_id == 2


def test_match_corners_across_laps():
    lap1 = _synthetic_lap(corner_count=3)
    lap2 = _synthetic_lap(corner_count=3)
    c1 = detect_corners(lap1)
    c2 = detect_corners(lap2)
    pairs = match_corners_across_laps(c1, c2)
    assert len(pairs) == 3
    for ref, other in pairs:
        assert abs(ref.lap_dist_apex - other.lap_dist_apex) < 50
