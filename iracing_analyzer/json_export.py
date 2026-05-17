"""Export full analysis data to JSON for the web frontend."""
from __future__ import annotations

import json
import math
import pathlib
from typing import Any

from .hardware_db import HardwareRecommendation
from .metrics.registry import MetricsResult
from .mermaid_gen import build_weakness_flow
from .ranking import Weakness
from .recommendations.ingame_config import SettingRecommendation
from .recommendations.practice_plan import PracticeDrill
from .report import DriverContext
from .root_cause import HardwareInfo


_DOWNSAMPLE_POINTS = 600  # target data points per lap per channel


def _downsample(data: list, n: int) -> list:
    if not data or len(data) <= n:
        return [v if v is not None else 0 for v in data]
    step = len(data) / n
    return [data[int(i * step)] or 0 for i in range(n)]


def _safe(v):
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def export_json(
    metrics: MetricsResult,
    weaknesses: list[Weakness],
    hardware: HardwareInfo,
    hw_recs: list[HardwareRecommendation],
    settings: list[SettingRecommendation],
    drills: list[PracticeDrill],
    driver: DriverContext,
    output_path: str | pathlib.Path,
) -> None:
    ref = metrics.reference_lap

    meta = {
        "driver": driver.name,
        "car": driver.car,
        "track": driver.track,
        "irating": driver.irating,
        "target": driver.target,
        "wheel": hardware.wheel_model,
        "wheel_torque_nm": hardware.wheel_torque_nm,
        "pedals": hardware.pedals_model,
        "pedals_type": hardware.pedals_type,
        "has_rig": hardware.has_rig,
        "ref_lap_number": ref.lap_number if ref else None,
        "ref_lap_time_s": _safe(ref.lap_time_s) if ref else None,
        "total_valid_laps": len(metrics.laps),
        "sample_rate_hz": metrics.session.sample_rate_hz,
        "source_file": metrics.session.source_path,
    }

    laps_data = []
    for lm in metrics.lap_metrics:
        laps_data.append({
            "lap_number": lm.lap.lap_number,
            "lap_time_s": _safe(lm.lap.lap_time_s),
            "is_reference": lm.lap is ref,
            "mean_brake_rate": _safe(lm.mean_brake_rate),
            "mean_trail_brake_pct": _safe(lm.mean_trail_brake_pct),
            "throttle_smoothness": _safe(lm.throttle_smoothness),
            "throttle_blips": lm.throttle_blips,
            "steering_jitter_rms": _safe(lm.steering_jitter_rms),
            "over_corrections": lm.over_corrections,
            "total_speed_cost_s": _safe(lm.total_speed_cost_s),
            "corner_count": len(lm.corners),
        })

    weaknesses_data = []
    for w in weaknesses:
        weaknesses_data.append({
            "key": w.key,
            "name": w.name,
            "metric_value": _safe(w.metric_value) if isinstance(w.metric_value, float) else str(w.metric_value),
            "metric_unit": w.metric_unit,
            "lap_time_cost_s": _safe(w.lap_time_cost_s),
            "cost_math": w.cost_math,
            "root_cause": w.root_cause.value,
            "root_cause_justification": w.root_cause_justification,
            "inference_flag": w.inference_flag,
            "corner_ids": w.corner_ids,
        })

    corners_data = []
    all_corner_ids = sorted(metrics.brake_cv_by_corner.keys())
    for cid in all_corner_ids:
        cv = metrics.brake_cv_by_corner.get(cid, 0)
        # find average speed deficit for this corner
        speed_costs = []
        for lm in metrics.lap_metrics:
            if lm.lap is ref:
                continue
            for d in lm.speed_deltas:
                if d.corner_id == cid:
                    speed_costs.append(d.delta_mps)
        avg_speed_deficit = sum(speed_costs) / len(speed_costs) if speed_costs else 0
        corners_data.append({
            "corner_id": cid,
            "brake_cv": _safe(cv),
            "mean_speed_deficit_mps": _safe(avg_speed_deficit),
        })

    # Telemetry traces: downsample key channels per lap, keyed by lap_dist_m
    channels_to_trace = ["Speed", "Brake", "Throttle", "SteeringWheelAngle", "LapDist"]
    telemetry: dict[str, Any] = {}
    for lm in metrics.lap_metrics:
        d = lm.lap.data
        lap_dist = d.get("LapDist") or []
        n = _DOWNSAMPLE_POINTS
        entry: dict[str, list] = {}
        for ch in channels_to_trace:
            raw = d.get(ch)
            if raw:
                entry[ch] = _downsample(raw, n)
        if entry:
            telemetry[str(lm.lap.lap_number)] = entry

    settings_data = []
    for s in settings:
        settings_data.append({
            "name": s.setting_name,
            "ui_path": s.ui_path,
            "value": s.recommended_value,
            "rationale": s.rationale,
            "source": s.source,
        })

    drills_data = []
    for d in drills:
        drills_data.append({
            "priority": d.priority,
            "title": d.title,
            "weakness_addressed": d.weakness_addressed,
            "description": d.description,
            "success_criterion": d.success_criterion,
            "session_format": d.session_format,
            "channel_to_monitor": d.channel_to_monitor,
        })

    all_no_upgrade = all(r.verdict == "no_upgrade_needed" for r in hw_recs)
    hw_verdict = "not_bottleneck" if all_no_upgrade else "upgrade_recommended"

    payload = {
        "meta": meta,
        "laps": laps_data,
        "weaknesses": weaknesses_data,
        "corners": corners_data,
        "telemetry": telemetry,
        "settings": settings_data,
        "drills": drills_data,
        "hardware_verdict": hw_verdict,
        "mermaid": build_weakness_flow(weaknesses),
        "channels_available": metrics.session.channels_available,
        "missing_channels": metrics.session.missing_channels,
    }

    out = pathlib.Path(output_path)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
