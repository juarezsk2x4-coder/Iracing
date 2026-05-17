"""Interactive CLI entry point."""
from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any

from .hardware_db import recommend_hardware
from .ibt_parser import load_session
from .json_export import export_json
from .loop import post_analysis_loop
from .metrics.registry import compute_metrics
from .ranking import rank_weaknesses
from .recommendations.ingame_config import generate_settings
from .recommendations.practice_plan import generate_drills
from .report import DriverContext, render_report
from .root_cause import HardwareInfo, classify_weaknesses


PEDAL_TYPES = {
    "1": "potentiometer",
    "2": "hall_effect",
    "3": "load_cell",
    "4": "hydraulic",
}


def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{label}{suffix}: ").strip()
    return val or default


def _prompt_float(label: str, default: float) -> float:
    raw = _prompt(label, str(default))
    try:
        return float(raw)
    except ValueError:
        return default


def _prompt_int(label: str, default: int) -> int:
    raw = _prompt(label, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def conversational_prompt(args: argparse.Namespace) -> tuple[HardwareInfo, DriverContext, str]:
    print("\niRacing Telemetry Analyzer — interactive mode")
    print("=" * 50)

    ibt_path = args.ibt
    while not ibt_path:
        ibt_path = _prompt("Path to .ibt or .ibt.zip file")
        if ibt_path and not pathlib.Path(ibt_path).expanduser().exists():
            print(f"  ✗ File not found: {ibt_path}")
            ibt_path = ""

    car = args.car or _prompt("Car (e.g. 'Porsche 911 GT3 R (992)')")
    track = args.track or _prompt("Track (e.g. 'Road Atlanta')")
    wheel = args.wheel or _prompt("Wheelbase model (e.g. 'Simagic Alpha Ultimate')")
    wheel_nm = args.wheel_torque or _prompt_float("Wheelbase peak torque (Nm)", 18.0)
    pedals = args.pedals or _prompt("Pedals model (e.g. 'Simagic P2000')")
    print("Pedal type: 1=potentiometer, 2=hall_effect, 3=load_cell, 4=hydraulic")
    ptype_raw = _prompt("Choose pedal type", "4")
    pedal_type = PEDAL_TYPES.get(ptype_raw, "load_cell")
    rig = (args.rig if args.rig is not None else _prompt("Mounted on a rig? (y/n)", "y").lower().startswith("y"))
    driver_name = args.driver or _prompt("Driver name", "")
    irating = args.irating or _prompt_int("Current iRating", 1500)
    target = args.target or _prompt("Target / goals", "consistent improvement")
    budget = args.budget if args.budget is not None else _prompt_float("Hardware upgrade budget (USD, 0 = none)", 0.0)
    brand = args.brand or _prompt("Brand constraint (e.g. 'Simagic', 'any')", "any")

    hardware = HardwareInfo(
        wheel_model=wheel,
        wheel_torque_nm=wheel_nm,
        pedals_model=pedals,
        pedals_type=pedal_type,
        has_rig=rig,
        notes=args.notes or "",
    )
    driver = DriverContext(
        name=driver_name,
        irating=irating,
        license_class="",
        target=target,
        car=car,
        track=track,
        budget_usd=budget,
        brand_constraint=brand,
    )
    return hardware, driver, ibt_path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="iracing-analyze",
        description="iRacing .ibt telemetry analyzer",
    )
    p.add_argument("--ibt", help="Path to .ibt or .ibt.zip file")
    p.add_argument("--car", help="Car name")
    p.add_argument("--track", help="Track name")
    p.add_argument("--wheel", help="Wheelbase model")
    p.add_argument("--wheel-torque", type=float, help="Wheelbase peak torque in Nm")
    p.add_argument("--pedals", help="Pedals model")
    p.add_argument("--pedal-type", choices=list(PEDAL_TYPES.values()))
    p.add_argument("--rig", type=lambda v: v.lower() in ("y", "yes", "true", "1"))
    p.add_argument("--driver", help="Driver name")
    p.add_argument("--irating", type=int)
    p.add_argument("--target", help="Driver goal")
    p.add_argument("--budget", type=float, help="Hardware upgrade budget USD")
    p.add_argument("--brand", help="Brand constraint")
    p.add_argument("--notes", help="Extra hardware notes")
    p.add_argument("--output", help="Write report to this Markdown file (default: stdout)")
    p.add_argument("--no-loop", action="store_true", help="Skip interactive follow-up loop")
    p.add_argument("--non-interactive", action="store_true",
                   help="Fail rather than prompt if any required input is missing")
    return p


def run_analysis(hardware: HardwareInfo, driver: DriverContext, ibt_path: str):
    """Run the full pipeline. Returns (report_md, metrics, weaknesses, hw_recs, settings, drills)."""
    print(f"\n→ Loading {ibt_path} ...")
    session = load_session(ibt_path, print_inventory=True)
    print(f"→ Computing metrics across {session.total_samples} samples at {session.sample_rate_hz:.0f} Hz ...")
    metrics = compute_metrics(session)
    if not metrics.lap_metrics:
        return "# Analysis Failed\n\nNo valid laps detected in this file.", metrics, [], [], [], []
    print(f"→ Detected {len(metrics.laps)} valid laps; reference lap = {metrics.reference_lap.lap_number}")
    weaknesses = rank_weaknesses(metrics)
    classify_weaknesses(weaknesses, hardware)
    hw_recs = recommend_hardware(
        weaknesses, hardware, driver.budget_usd, driver.brand_constraint
    )
    settings = generate_settings(weaknesses, hardware, driver.car)
    drills = generate_drills(weaknesses, max_drills=3)
    report = render_report(metrics, weaknesses, hardware, hw_recs, settings, drills, driver)
    return report, metrics, weaknesses, hw_recs, settings, drills


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.non_interactive and not args.ibt:
        parser.error("--ibt is required in --non-interactive mode")

    try:
        if args.non_interactive:
            hardware = HardwareInfo(
                wheel_model=args.wheel or "",
                wheel_torque_nm=args.wheel_torque or 0.0,
                pedals_model=args.pedals or "",
                pedals_type=args.pedal_type or "unknown",
                has_rig=bool(args.rig),
                notes=args.notes or "",
            )
            driver = DriverContext(
                name=args.driver or "",
                irating=args.irating or 0,
                target=args.target or "",
                car=args.car or "",
                track=args.track or "",
                budget_usd=args.budget or 0.0,
                brand_constraint=args.brand or "any",
            )
            ibt_path = args.ibt
        else:
            hardware, driver, ibt_path = conversational_prompt(args)

        report, metrics, weaknesses, hw_recs, settings, drills = run_analysis(hardware, driver, ibt_path)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1

    if args.output:
        out_path = pathlib.Path(args.output).expanduser()
        out_path.write_text(report)
        print(f"\n✓ Report written to {out_path}")
        json_path = out_path.with_suffix(".json")
        export_json(metrics, weaknesses, hardware, hw_recs, settings, drills, driver, json_path)
        print(f"✓ Data exported to  {json_path}")
    else:
        print("\n" + "=" * 50)
        print(report)

    if not args.no_loop and not args.non_interactive:
        post_analysis_loop(metrics, weaknesses, hardware, driver)
    return 0


if __name__ == "__main__":
    sys.exit(main())
