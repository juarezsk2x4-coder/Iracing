"""Post-analysis interactive follow-up loop."""
from __future__ import annotations

import pathlib

from .hardware_db import recommend_hardware
from .ibt_parser import load_session
from .metrics.registry import MetricsResult, compute_metrics
from .ranking import Weakness, rank_weaknesses
from .recommendations.ingame_config import generate_settings
from .recommendations.practice_plan import generate_drills
from .report import DriverContext, render_report
from .root_cause import HardwareInfo, classify_weaknesses


def post_analysis_loop(
    metrics: MetricsResult,
    weaknesses: list[Weakness],
    hardware: HardwareInfo,
    driver: DriverContext,
) -> None:
    while True:
        print("\n" + "-" * 50)
        print("Follow-up options:")
        print("  1. Drill into a specific weakness")
        print("  2. Compare this session with a second .ibt file")
        print("  3. Log a practice-session result")
        print("  4. Exit")
        choice = input("> ").strip()
        if choice == "1":
            _drill_into_weakness(metrics, weaknesses)
        elif choice == "2":
            _compare_with_second(metrics, weaknesses, hardware, driver)
        elif choice == "3":
            _log_practice_result(weaknesses)
        elif choice in ("4", "q", "quit", "exit", ""):
            print("Done.")
            return
        else:
            print("Unrecognized choice.")


def _drill_into_weakness(metrics: MetricsResult, weaknesses: list[Weakness]) -> None:
    if not weaknesses:
        print("No weaknesses to drill into.")
        return
    print("\nWeaknesses:")
    for i, w in enumerate(weaknesses, start=1):
        print(f"  {i}. {w.name} (~{w.lap_time_cost_s:.3f}s/lap)")
    raw = input("Pick number: ").strip()
    try:
        idx = int(raw) - 1
        w = weaknesses[idx]
    except (ValueError, IndexError):
        print("Invalid choice.")
        return
    print(f"\n--- {w.name} ---")
    print(f"Metric value: {w.metric_value} {w.metric_unit}")
    print(f"Cost math: {w.cost_math}")
    print(f"Root cause: {w.root_cause.value}")
    print(f"Justification: {w.root_cause_justification}")
    if w.corner_ids:
        print(f"Worst corners: T{', T'.join(str(c) for c in w.corner_ids)}")
    # Per-lap detail
    print("\nPer-lap values:")
    for lm in metrics.lap_metrics:
        val = _per_lap_value(lm, w.key)
        marker = " ← reference" if lm.lap is metrics.reference_lap else ""
        print(f"  Lap {lm.lap.lap_number}: {val}{marker}")


def _per_lap_value(lm, key: str) -> str:
    if key == "trail_braking":
        v = lm.mean_trail_brake_pct
        return f"{v:.2f}% trail-brake" if v is not None else "n/a"
    if key == "brake_cv":
        if not lm.brake_zones:
            return "no zones"
        return f"{len(lm.brake_zones)} zones, mean peak={sum(z.peak_pressure for z in lm.brake_zones)/len(lm.brake_zones):.3f}"
    if key == "steering_jitter":
        v = lm.steering_jitter_rms
        return f"{v:.4f} rad RMS" if v is not None else "n/a"
    if key == "throttle_blips":
        return f"{lm.throttle_blips} blips"
    if key == "throttle_smoothness":
        return f"{lm.throttle_smoothness:.4f} jerk"
    if key == "brake_rate":
        return f"{lm.mean_brake_rate:.1f} %/100ms"
    if key == "mid_corner_speed":
        return f"{lm.total_speed_cost_s:.3f}s vs reference"
    return "n/a"


def _compare_with_second(
    metrics: MetricsResult,
    weaknesses: list[Weakness],
    hardware: HardwareInfo,
    driver: DriverContext,
) -> None:
    path = input("Path to second .ibt or .ibt.zip: ").strip()
    if not path or not pathlib.Path(path).expanduser().exists():
        print("File not found.")
        return
    print("Loading and analyzing comparison file...")
    session2 = load_session(path, print_inventory=False)
    metrics2 = compute_metrics(session2)
    if not metrics2.lap_metrics:
        print("Second file has no valid laps.")
        return
    weaknesses2 = rank_weaknesses(metrics2)
    classify_weaknesses(weaknesses2, hardware)

    by_key1 = {w.key: w for w in weaknesses}
    by_key2 = {w.key: w for w in weaknesses2}
    all_keys = sorted(set(by_key1) | set(by_key2))
    print("\nComparison:")
    print(f"{'Weakness':30s} {'Session 1':>12s} {'Session 2':>12s} {'Δ':>10s}")
    print("-" * 70)
    for k in all_keys:
        c1 = by_key1[k].lap_time_cost_s if k in by_key1 else 0.0
        c2 = by_key2[k].lap_time_cost_s if k in by_key2 else 0.0
        delta = c2 - c1
        arrow = "↓" if delta < -0.005 else ("↑" if delta > 0.005 else "→")
        print(f"{k:30s} {c1:>10.3f}s {c2:>10.3f}s {arrow} {delta:>+7.3f}s")


def _log_practice_result(weaknesses: list[Weakness]) -> None:
    if not weaknesses:
        print("Nothing to log.")
        return
    drills = generate_drills(weaknesses, max_drills=3)
    print("\nCurrent drills:")
    for d in drills:
        print(f"  {d.priority}. {d.title} — target: {d.success_criterion}")
    drill_idx = input("Which drill did you practice (number)? ").strip()
    try:
        drill = drills[int(drill_idx) - 1]
    except (ValueError, IndexError):
        print("Invalid choice.")
        return
    outcome = input(f"Outcome for '{drill.title}' (pass/partial/fail): ").strip().lower()
    notes = input("Notes: ").strip()
    log_path = pathlib.Path.cwd() / "practice_log.txt"
    with open(log_path, "a") as f:
        f.write(f"{drill.title}\t{outcome}\t{notes}\n")
    print(f"Logged to {log_path}")
