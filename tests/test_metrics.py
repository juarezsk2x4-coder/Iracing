"""Unit tests for brake / throttle / steering metrics."""
import math

from iracing_analyzer.corner_detector import detect_corners
from iracing_analyzer.lap_splitter import LapData
from iracing_analyzer.metrics.brake_metrics import (
    extract_brake_zones,
    mean_application_rate,
    mean_trail_brake_pct,
    peak_pressure_cv,
)
from iracing_analyzer.metrics.steering_metrics import steering_jitter_rms
from iracing_analyzer.metrics.throttle_metrics import (
    throttle_blip_count,
    throttle_smoothness_score,
)


def _lap_with_brake_and_steer(rate: float = 60.0, corner_count: int = 2) -> LapData:
    samples_per_corner = 300
    total = samples_per_corner * corner_count
    speed: list[float] = []
    brake: list[float] = []
    throttle: list[float] = []
    steering: list[float] = []
    lat: list[float] = []
    for i in range(total):
        w = i % samples_per_corner
        speed.append(60.0 - 35.0 * (1 - math.cos(2 * math.pi * w / samples_per_corner)) / 2)
        # brake ramps up before apex (samples 50-150), peaks at 100, releases by 200
        if 30 <= w <= 100:
            brake.append((w - 30) / 70.0 * 0.85)
        elif 100 < w <= 200:
            brake.append(max(0.0, 0.85 - (w - 100) / 100.0 * 0.85))
        else:
            brake.append(0.0)
        # throttle: zero in braking, ramps in exit
        if w > 150:
            throttle.append(min(1.0, (w - 150) / 100.0))
        else:
            throttle.append(0.0)
        # steering: zero before turn-in, ramps in cornering
        if 100 < w < 250:
            steering.append(math.sin(math.pi * (w - 100) / 150) * 0.4)
        else:
            steering.append(0.0)
        lat.append(-10.0 * (1 - math.cos(2 * math.pi * w / samples_per_corner)) / 2)
    return LapData(
        lap_number=1,
        start_sample=0,
        end_sample=total,
        lap_time_s=total / rate,
        is_valid=True,
        data={
            "Speed": speed,
            "Brake": brake,
            "Throttle": throttle,
            "SteeringWheelAngle": steering,
            "LateralAccel": lat,
            "LapDist": list(range(total)),
        },
        sample_rate_hz=rate,
    )


def test_brake_zones_extracted():
    lap = _lap_with_brake_and_steer(corner_count=2)
    corners = detect_corners(lap)
    zones = extract_brake_zones(lap, corners)
    assert len(zones) == 2
    for z in zones:
        assert 0.5 < z.peak_pressure <= 1.0
        assert z.application_rate_pct_per_100ms > 0


def test_trail_brake_overlap_detected():
    lap = _lap_with_brake_and_steer(corner_count=2)
    corners = detect_corners(lap)
    zones = extract_brake_zones(lap, corners)
    trail_pct = mean_trail_brake_pct(zones, lap.duration_s)
    assert trail_pct is not None and trail_pct > 0


def test_brake_cv_empty_when_one_lap():
    lap = _lap_with_brake_and_steer(corner_count=2)
    corners = detect_corners(lap)
    zones = extract_brake_zones(lap, corners)
    cv = peak_pressure_cv([zones])
    assert cv == {}, "CV undefined for n<2 observations per corner"


def test_throttle_smoothness_low_for_clean_ramp():
    lap = _lap_with_brake_and_steer(corner_count=2)
    corners = detect_corners(lap)
    score = throttle_smoothness_score(lap, corners)
    assert score >= 0.0
    assert score < 0.01, "smooth ramp should produce low jerk score"


def test_throttle_blips_zero_for_monotonic():
    lap = _lap_with_brake_and_steer(corner_count=2)
    corners = detect_corners(lap)
    blips = throttle_blip_count(lap, corners)
    assert blips == 0


def test_steering_jitter_returns_none_if_missing():
    lap = _lap_with_brake_and_steer(corner_count=2)
    lap.data.pop("SteeringWheelAngle")
    corners = detect_corners(lap)
    assert steering_jitter_rms(lap, corners) is None


def test_steering_jitter_low_for_smooth_input():
    lap = _lap_with_brake_and_steer(corner_count=2)
    corners = detect_corners(lap)
    jitter = steering_jitter_rms(lap, corners)
    assert jitter is not None and jitter < 0.01


def test_brake_application_rate_mean_positive():
    lap = _lap_with_brake_and_steer(corner_count=2)
    corners = detect_corners(lap)
    zones = extract_brake_zones(lap, corners)
    assert mean_application_rate(zones) > 0
