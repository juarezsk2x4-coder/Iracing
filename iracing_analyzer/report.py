"""Assemble the final Markdown analysis report."""
from __future__ import annotations

from dataclasses import dataclass

from .hardware_db import HardwareRecommendation
from .mermaid_gen import build_weakness_flow
from .metrics.registry import MetricsResult
from .ranking import RootCause, Weakness
from .recommendations.ingame_config import SettingRecommendation
from .recommendations.practice_plan import PracticeDrill
from .root_cause import HardwareInfo


@dataclass
class DriverContext:
    name: str = ""
    irating: int = 0
    license_class: str = ""
    target: str = ""
    car: str = ""
    track: str = ""
    budget_usd: float = 0.0
    brand_constraint: str = ""


def render_report(
    metrics: MetricsResult,
    weaknesses: list[Weakness],
    hardware: HardwareInfo,
    hw_recs: list[HardwareRecommendation],
    settings: list[SettingRecommendation],
    drills: list[PracticeDrill],
    driver: DriverContext,
) -> str:
    parts: list[str] = []
    parts.append(_header(metrics, driver, hardware))
    parts.append(_summary_bullets(weaknesses, hw_recs, settings, drills))
    parts.append(_channel_inventory(metrics))
    parts.append(_section_diagnostic(metrics, weaknesses))
    parts.append(_section_hardware(hw_recs, hardware))
    parts.append(_section_settings(settings))
    parts.append(_section_practice(drills))
    parts.append("## Decision Flow\n\n" + build_weakness_flow(weaknesses))
    parts.append(_footer())
    return "\n\n".join(parts)


def _header(metrics: MetricsResult, driver: DriverContext, hardware: HardwareInfo) -> str:
    laps = len(metrics.laps)
    ref = metrics.reference_lap
    ref_time = f"{ref.lap_time_s:.3f}s (lap {ref.lap_number})" if ref else "n/a"
    return (
        f"# iRacing Telemetry Analysis\n\n"
        f"- **Driver**: {driver.name or 'n/a'} "
        f"({driver.irating or 'n/a'} iR, target: {driver.target or 'n/a'})\n"
        f"- **Car**: {driver.car or 'n/a'}\n"
        f"- **Track**: {driver.track or 'n/a'}\n"
        f"- **Hardware**: {hardware.wheel_model} ({hardware.wheel_torque_nm:.1f} Nm DD) + "
        f"{hardware.pedals_model} ({hardware.pedals_type})\n"
        f"- **Laps analyzed**: {laps} valid\n"
        f"- **Reference lap**: {ref_time}\n"
        f"- **Source**: `{metrics.session.source_path}`"
    )


def _summary_bullets(
    weaknesses: list[Weakness],
    hw_recs: list[HardwareRecommendation],
    settings: list[SettingRecommendation],
    drills: list[PracticeDrill],
) -> str:
    top_w = weaknesses[0] if weaknesses else None
    hardware_verdict = "your current hardware is not the bottleneck"
    if any(r.verdict == "upgrade_recommended" for r in hw_recs):
        upgrade = next(r for r in hw_recs if r.verdict == "upgrade_recommended")
        hardware_verdict = (
            f"consider upgrading for {upgrade.weakness_key}: {upgrade.product['name']}"
        )
    key_setting = settings[1] if len(settings) > 1 else (settings[0] if settings else None)
    top_drill = drills[0] if drills else None
    lines = ["## Summary"]
    if top_w:
        lines.append(
            f"- **Top weakness**: {top_w.name} — ~{top_w.lap_time_cost_s:.3f}s/lap "
            f"({top_w.root_cause.value})"
        )
    else:
        lines.append("- **Top weakness**: none detected above noise floor")
    lines.append(f"- **Hardware verdict**: {hardware_verdict}")
    if key_setting:
        lines.append(
            f"- **Key setting change**: {key_setting.setting_name} → {key_setting.recommended_value}"
        )
    if top_drill:
        lines.append(f"- **Top drill**: {top_drill.title}")
    return "\n".join(lines)


def _channel_inventory(metrics: MetricsResult) -> str:
    lines = ["## Channel Inventory"]
    lines.append("| Channel | Unit | Available |")
    lines.append("|---|---|---|")
    available = set(metrics.session.channels_available)
    rows = []
    for ch in ["Speed", "Brake", "Throttle", "Lap", "SteeringWheelAngle",
               "LapDist", "LateralAccel", "OnPitRoad", "LapLastLapTime",
               "BrakeRaw", "Gear", "RPM"]:
        ok = "✅" if ch in available else "❌"
        unit = metrics.session.channel_meta.get(ch).unit if ch in metrics.session.channel_meta else "—"
        rows.append(f"| `{ch}` | {unit} | {ok} |")
    lines.extend(rows)
    if metrics.session.missing_channels:
        lines.append("")
        lines.append(
            f"_Missing optional channels: {', '.join(metrics.session.missing_channels)}._ "
            "Affected metrics are flagged inline as **[CHANNEL UNAVAILABLE — inferred]**."
        )
    return "\n".join(lines)


def _section_diagnostic(metrics: MetricsResult, weaknesses: list[Weakness]) -> str:
    if not weaknesses:
        return "## 1. Telemetry Diagnostic\n\nNo significant weaknesses detected above noise floor."
    lines = ["## 1. Telemetry Diagnostic"]
    lines.append("Weaknesses ranked by estimated lap-time cost (highest first):")
    lines.append("")
    for i, w in enumerate(weaknesses, start=1):
        cost = f"~{w.lap_time_cost_s:.3f}s/lap"
        flag = (
            f" **[CHANNEL UNAVAILABLE — inferred]**" if w.inference_flag else ""
        )
        lines.append(f"### {i}. {w.name}{flag}")
        lines.append(f"- **Estimated cost**: {cost}")
        if isinstance(w.metric_value, (int, float)):
            lines.append(f"- **Metric value**: {w.metric_value:.4f} {w.metric_unit}")
        else:
            lines.append(f"- **Metric value**: {w.metric_value} {w.metric_unit}")
        lines.append(f"- **Cost math**: `{w.cost_math}`")
        lines.append(f"- **Channels used**: {', '.join(f'`{c}`' for c in w.channels_used)}")
        if w.corner_ids:
            lines.append(f"- **Worst corners**: T{', T'.join(str(cid) for cid in w.corner_ids)}")
        lines.append(f"- **Root cause**: **{w.root_cause.value}** — {w.root_cause_justification}")
        if w.inference_flag:
            lines.append(f"- **Inference flag**: {w.inference_flag}")
        lines.append("")
    return "\n".join(lines)


def _section_hardware(recs: list[HardwareRecommendation], hardware: HardwareInfo) -> str:
    lines = ["## 2. Hardware Recommendation"]
    all_no_upgrade = all(r.verdict == "no_upgrade_needed" for r in recs)
    if all_no_upgrade or not recs:
        lines.append(
            f"**Verdict: your current hardware is not the bottleneck.** "
            f"The {hardware.wheel_model} delivers {hardware.wheel_torque_nm:.1f} Nm DD, "
            f"and the {hardware.pedals_model} ({hardware.pedals_type}) eliminates the "
            "load-cell-vs-potentiometer noise problem that limits entry-level rigs. "
            "Every diagnosed weakness in this session traces to technique or in-game settings."
        )
        lines.append("")
        lines.append(
            "Counter-argument: a higher-torque wheel could in theory deliver more detail near "
            "the limit, but the telemetry shows no signal that the hardware is masking driver "
            "intent. Spend the money on iRacing subscriptions and coaching instead."
        )
        return "\n".join(lines)

    for r in recs:
        if r.verdict == "no_upgrade_needed":
            continue
        lines.append(f"### {r.weakness_key}")
        lines.append(f"- {r.summary}")
        if r.product:
            lines.append(
                f"- **Product**: {r.product['name']} "
                f"(${r.product.get('price_usd', 0):.0f}; ~R${r.product.get('price_brl_estimate', 0):.0f})"
            )
            for s in r.product.get("strengths", []):
                lines.append(f"  - + {s}")
            for w_ in r.product.get("weaknesses", []):
                lines.append(f"  - − {w_}")
        if r.brazil_note:
            lines.append(f"- **Brazil import note**: {r.brazil_note}")
        lines.append(f"- **Counter-argument**: {r.counter_argument}")
        lines.append("")
    return "\n".join(lines)


def _section_settings(settings: list[SettingRecommendation]) -> str:
    lines = ["## 3. In-Game Configuration"]
    if not settings:
        lines.append("_No settings adjustments recommended._")
        return "\n".join(lines)
    for s in settings:
        lines.append(f"### {s.setting_name}")
        lines.append(f"- **iRacing path**: `{s.ui_path}`")
        lines.append(f"- **Recommended**: {s.recommended_value}")
        lines.append(f"- **Why**: {s.rationale}")
        lines.append(f"- **Source**: {s.source}")
        # Critique
        lines.append(
            f"- **Risk**: settings changes feel different immediately; do not chase lap time "
            "in the first session after changing them — focus on consistency."
        )
        lines.append("")
    return "\n".join(lines)


def _section_practice(drills: list[PracticeDrill]) -> str:
    lines = ["## 4. Practice Plan"]
    if not drills:
        lines.append("_No drills generated — insufficient weakness signal._")
        return "\n".join(lines)
    for d in drills:
        lines.append(f"### Drill {d.priority}: {d.title}")
        lines.append(f"- **Addresses**: {d.weakness_addressed}")
        lines.append(f"- **What to do**: {d.description}")
        lines.append(f"- **Success criterion**: {d.success_criterion}")
        lines.append(f"- **Session format**: {d.session_format}")
        lines.append(f"- **Monitor**: `{d.channel_to_monitor}`")
        lines.append("")
    return "\n".join(lines)


def _footer() -> str:
    return (
        "## Notes\n\n"
        "- Heuristic lap-time costs labeled `[HEURISTIC]` are approximations, not measurements. "
        "Use them to order priorities, not to set targets.\n"
        "- Physics-based costs (corner speed delta) are first-order kinematic estimates assuming "
        "constant corner length; actual gains depend on the rest of the lap holding constant.\n"
        "- Re-run analysis after one practice session per drill to validate improvement."
    )
