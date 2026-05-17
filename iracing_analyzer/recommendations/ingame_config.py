"""iRacing in-game configuration recommendations with exact UI paths."""
from __future__ import annotations

from dataclasses import dataclass

from ..ranking import Weakness
from ..root_cause import HardwareInfo


@dataclass
class SettingRecommendation:
    setting_name: str
    ui_path: str
    recommended_value: str
    rationale: str
    source: str


def generate_settings(
    weaknesses: list[Weakness],
    hardware: HardwareInfo,
    car: str = "",
) -> list[SettingRecommendation]:
    recs: list[SettingRecommendation] = []
    keys = {w.key for w in weaknesses}

    # FFB strength — auto-set via in-car Black Box rather than guessing
    recs.append(SettingRecommendation(
        setting_name="Force Feedback Strength",
        ui_path="Black Box (F9 in-car) > Force Feedback > 'Auto' button",
        recommended_value="Use 'Auto' once per car after 1-2 hot laps; verify the bar is not flashing red",
        rationale=(
            f"With a {hardware.wheel_torque_nm:.0f} Nm DD wheel, hand-tuning FFB strength risks "
            "clipping on high-grip cars. iRacing's Auto sets max torque without clipping, "
            "which is the correct ceiling for a DD wheel."
        ),
        source="iRacing Member Forums — David Tucker FFB documentation",
    ))

    # Damping — settings-side fix for steering jitter on DD
    if "steering_jitter" in keys:
        recs.append(SettingRecommendation(
            setting_name="Force Feedback Damping",
            ui_path="Options > Drive > Force Feedback > Damping",
            recommended_value="5-10% on DD wheels (start at 5; increase by 1 until jitter quiets)",
            rationale=(
                "Damping suppresses high-frequency oscillations the DD motor amplifies. "
                "With Simagic Alpha class hardware, do NOT exceed 10% or the wheel will feel laggy."
            ),
            source="iRacing Member Guide; Boosted Media FFB Setup Guide",
        ))
    else:
        recs.append(SettingRecommendation(
            setting_name="Force Feedback Damping",
            ui_path="Options > Drive > Force Feedback > Damping",
            recommended_value="0-5%",
            rationale="No jitter symptoms in telemetry; keep damping minimal to preserve detail.",
            source="iRacing default guidance",
        ))

    # Min Force — usually 0 on DD
    recs.append(SettingRecommendation(
        setting_name="Min Force",
        ui_path="Options > Drive > Force Feedback > Min Force",
        recommended_value="0%",
        rationale="DD wheels have no deadzone; Min Force only helps belt/gear wheels.",
        source="iRacing Member Forums",
    ))

    # Smoothing — never on DD wheels
    recs.append(SettingRecommendation(
        setting_name="Smoothing",
        ui_path="Options > Drive > Force Feedback > Smoothing",
        recommended_value="0",
        rationale="Smoothing destroys the road texture that DD hardware exists to deliver.",
        source="Boosted Media FFB Setup Guide",
    ))

    # Brake force factor — load-cell / hydraulic = linear
    if hardware.is_high_quality_pedals:
        recs.append(SettingRecommendation(
            setting_name="Brake Force Factor",
            ui_path="Options > Drive > Pedals > Brake Force Factor (or Brake Calibration)",
            recommended_value="1.0 (linear); set max-pressure point so 100% brake = comfortable peak press",
            rationale=(
                f"{hardware.pedals_model} reports real pressure. Anything other than linear hides "
                "what the pedal is actually doing."
            ),
            source="iRacing Custom Brake App documentation",
        ))

    # LUT — only if brake CV is high
    if "brake_cv" in keys:
        recs.append(SettingRecommendation(
            setting_name="Brake Linearity Lookup Table (LUT)",
            ui_path="Documents/iRacing/braketable.txt (custom .lut) or Options > Drive > Pedals",
            recommended_value="Generate a per-driver brake LUT using the iRacing Custom Brake App",
            rationale=(
                "When brake-pressure consistency is the problem on hydraulic pedals, a LUT mapping "
                "raw pressure → game-brake response gives the driver a more linear feel and lets "
                "them hit the same peak repeatedly."
            ),
            source="iRacing Custom Brake App documentation",
        ))

    # Wheel rotation lock for the car
    recs.append(SettingRecommendation(
        setting_name="Steering Wheel Range (per car)",
        ui_path="Options > Drive > Steering Wheel: 'Auto' + verify with car's actual lock",
        recommended_value="Auto — let iRacing match game lock to the car (~480° for Porsche GT3 R)",
        rationale=(
            "Locking the wheel to the car's actual steering range means 1:1 visual feedback. "
            "Mid-corner speed deficits often trace to mismatched wheel ratio."
        ),
        source="iRacing Member Guide",
    ))

    # Look-ahead — for mid-corner speed weakness
    if "mid_corner_speed" in keys:
        recs.append(SettingRecommendation(
            setting_name="Look Ahead / Head Movement",
            ui_path="Options > Graphics > Driving View > Look Ahead",
            recommended_value="1.5-2.0 seconds (start at 1.5)",
            rationale=(
                "Carrying mid-corner speed requires eyes on the exit, not the apex. Increased look-ahead "
                "forces the camera to anticipate, which trains the driver's eyes."
            ),
            source="Coach Dave Academy — Vision and Look-Ahead Training",
        ))

    return recs
