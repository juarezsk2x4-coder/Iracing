"""Generate a prioritized 3-drill practice plan tied to the top weaknesses."""
from __future__ import annotations

from dataclasses import dataclass

from ..ranking import Weakness


@dataclass
class PracticeDrill:
    priority: int
    title: str
    weakness_addressed: str
    description: str
    success_criterion: str
    session_format: str
    channel_to_monitor: str


_DRILLS_BY_KEY: dict[str, PracticeDrill] = {
    "trail_braking": PracticeDrill(
        priority=0,
        title="Trail-Braking Overlap Drill",
        weakness_addressed="trail_braking",
        description=(
            "Pick 3 medium-speed corners. From threshold braking, intentionally hold ~20% brake "
            "pressure past turn-in, bleeding linearly to zero at apex. Do 10 laps focusing only on "
            "these corners; ignore lap time."
        ),
        success_criterion="Raise mean trail-braking % from current value to >5% of lap.",
        session_format="20-lap solo practice, same car/track, no AI",
        channel_to_monitor="Brake + SteeringWheelAngle overlap zone",
    ),
    "brake_cv": PracticeDrill(
        priority=0,
        title="Threshold Braking Consistency",
        weakness_addressed="brake_cv",
        description=(
            "Pick one heavy-braking corner. Set a target peak brake pressure (e.g. 85%). Run 15 laps. "
            "Goal: hit ±3% of that target every single lap. Do not chase lap time."
        ),
        success_criterion="Brake peak-pressure CV at the target corner < 0.07 across 10 consecutive laps.",
        session_format="15-lap solo practice, identical fuel/tyre conditions",
        channel_to_monitor="Brake peak pressure per corner",
    ),
    "mid_corner_speed": PracticeDrill(
        priority=0,
        title="Min-Corner Speed Hunting",
        weakness_addressed="mid_corner_speed",
        description=(
            "Pick the 3 corners with the largest delta vs. your best lap. Run 10 laps. Each lap, try "
            "to carry +2 km/h through the apex of those corners while keeping wheels on the track. "
            "Most attempts will fail — push until you find the new ceiling."
        ),
        success_criterion="Lift apex speed on each target corner by ≥ 3 km/h over the next session.",
        session_format="10-lap solo practice, log lap-by-lap apex speed",
        channel_to_monitor="Speed at apex_sample per corner",
    ),
    "steering_jitter": PracticeDrill(
        priority=0,
        title="Steering Calm — Single-Input Corners",
        weakness_addressed="steering_jitter",
        description=(
            "Run 10 laps deliberately making ONE smooth steering input per corner. If the car needs more "
            "lock mid-corner, you turned in too early; reset and try again. The goal is one input arc, "
            "not a series of corrections."
        ),
        success_criterion="Steering jitter RMS < 0.015 rad across all corners.",
        session_format="10-lap solo practice with FFB Damping = 5%",
        channel_to_monitor="SteeringWheelAngle high-pass RMS",
    ),
    "throttle_blips": PracticeDrill(
        priority=0,
        title="Commit-To-One Throttle",
        weakness_addressed="throttle_blips",
        description=(
            "Force yourself to make ONE throttle application per corner exit — no lifts, no re-applications. "
            "If the car oversteers, accept the slide and use it, or pick a different line next lap. The "
            "fix is line/entry, not throttle hesitation."
        ),
        success_criterion="<1 throttle blip per lap on average.",
        session_format="10-lap solo practice",
        channel_to_monitor="Throttle signal during corner exit",
    ),
    "throttle_smoothness": PracticeDrill(
        priority=0,
        title="Roll-On Throttle Ramp",
        weakness_addressed="throttle_smoothness",
        description=(
            "From apex, target a constant rate of throttle increase (e.g. 0 → 100% over 1.5 seconds). "
            "Use a metronome app set to ~80 BPM as a mental pacer. The goal is no spikes, no flats."
        ),
        success_criterion="Throttle jerk score < 0.015.",
        session_format="10-lap solo practice",
        channel_to_monitor="Throttle 2nd-derivative (jerk proxy)",
    ),
    "brake_rate": PracticeDrill(
        priority=0,
        title="Threshold Stab Drill",
        weakness_addressed="brake_rate",
        description=(
            "Practise pressing the brake to ~90% peak within 200ms. Use a short straight + heavy braking "
            "zone. Reach peak fast, then bleed off as you turn in. Hesitation is the enemy."
        ),
        success_criterion="Brake application rate 20-35 %/100ms.",
        session_format="10-lap solo practice in a heavy-braking corner",
        channel_to_monitor="Brake channel slope from onset to peak",
    ),
}


def generate_drills(weaknesses: list[Weakness], max_drills: int = 3) -> list[PracticeDrill]:
    """Map the top weaknesses to drills. Skip duplicates and missing keys."""
    out: list[PracticeDrill] = []
    seen: set[str] = set()
    for w in weaknesses:
        if w.key in seen:
            continue
        drill = _DRILLS_BY_KEY.get(w.key)
        if not drill:
            continue
        seen.add(w.key)
        drill_copy = PracticeDrill(
            priority=len(out) + 1,
            title=drill.title,
            weakness_addressed=w.name,
            description=drill.description,
            success_criterion=drill.success_criterion,
            session_format=drill.session_format,
            channel_to_monitor=drill.channel_to_monitor,
        )
        out.append(drill_copy)
        if len(out) >= max_drills:
            break
    return out
