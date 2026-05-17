"""Classify each ranked weakness as hardware / settings / technique / ambiguous."""
from __future__ import annotations

from dataclasses import dataclass

from .ranking import RootCause, Weakness


@dataclass
class HardwareInfo:
    wheel_model: str = ""
    wheel_torque_nm: float = 0.0
    pedals_model: str = ""
    pedals_type: str = "unknown"  # 'potentiometer' | 'hall_effect' | 'load_cell' | 'hydraulic'
    has_rig: bool = False
    notes: str = ""

    @property
    def is_direct_drive(self) -> bool:
        return self.wheel_torque_nm >= 8.0

    @property
    def is_high_quality_pedals(self) -> bool:
        return self.pedals_type in ("load_cell", "hydraulic")


def classify_weaknesses(
    weaknesses: list[Weakness],
    hardware: HardwareInfo,
) -> list[Weakness]:
    """Mutate each weakness with root_cause + justification."""
    for w in weaknesses:
        rc, just = _classify_one(w, hardware)
        w.root_cause = rc
        w.root_cause_justification = just
    return weaknesses


def _classify_one(w: Weakness, hw: HardwareInfo) -> tuple[RootCause, str]:
    if w.inference_flag:
        return RootCause.AMBIGUOUS, f"Insufficient data: {w.inference_flag}"

    if w.key == "steering_jitter":
        rms = float(w.metric_value) if isinstance(w.metric_value, (int, float)) else 0.0
        if hw.is_direct_drive:
            return (
                RootCause.SETTINGS,
                "DD wheel hardware is not the bottleneck — investigate FFB Damping/Smoothing settings "
                "and check for FFB clipping in the iRacing Black Box.",
            )
        return (
            RootCause.HARDWARE,
            "High jitter combined with belt/gear wheel suggests the wheelbase cannot deliver clean signal. "
            "Settings tuning alone is unlikely to fully resolve.",
        )

    if w.key == "brake_cv":
        if hw.is_high_quality_pedals:
            return (
                RootCause.TECHNIQUE,
                f"Pedals ({hw.pedals_model} / {hw.pedals_type}) already eliminate sensor noise. "
                "Inconsistency is in the foot — driver pressure modulation.",
            )
        return (
            RootCause.HARDWARE,
            "Potentiometer-style pedals introduce sensor drift that no technique can compensate for. "
            "A load-cell or hydraulic upgrade is warranted.",
        )

    if w.key == "brake_rate":
        rate = float(w.metric_value) if isinstance(w.metric_value, (int, float)) else 0.0
        if rate < 15.0:
            return (
                RootCause.TECHNIQUE,
                "Slow brake onset = driver not 'stabbing' the pedal at threshold. Drill: practise threshold "
                "braking with target peak achieved within 200ms.",
            )
        if rate > 50.0 and hw.is_high_quality_pedals:
            return (
                RootCause.SETTINGS,
                "Pedal hardware is fine but in-game Brake Force Factor may be set too low, causing user to "
                "over-press to reach peak — check Options > Drive > Pedals.",
            )
        return RootCause.TECHNIQUE, "Driver-controlled — apply pressure in two stages: max bite, then bleed."

    if w.key == "trail_braking":
        return (
            RootCause.TECHNIQUE,
            "Trail-braking is a technique decision. Drill: overlap brake release with steering input "
            "from corner entry through past apex.",
        )

    if w.key in ("throttle_blips", "throttle_smoothness"):
        return (
            RootCause.TECHNIQUE,
            "Hesitation / coarse throttle = driver second-guessing. Drill: commit to one throttle application "
            "per corner; if it doesn't work, change line, not throttle.",
        )

    if w.key == "mid_corner_speed":
        # mid-corner speed deficit is almost always technique unless the car balance is broken
        return (
            RootCause.TECHNIQUE,
            "Mid-corner speed is the sum of entry, line, and trust. Address by working on trail-braking "
            "and a later, slower turn-in to carry rotation.",
        )

    return RootCause.AMBIGUOUS, "No clear classification — review the metric manually."
