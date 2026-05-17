"""Load hardware database and emit hardware-bottleneck verdicts."""
from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Any

import yaml

from .ranking import RootCause, Weakness
from .root_cause import HardwareInfo


DEFAULT_DB_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "hardware_db.yaml"


@dataclass
class HardwareRecommendation:
    weakness_key: str
    verdict: str  # 'no_upgrade_needed' | 'upgrade_recommended' | 'sidegrade'
    summary: str
    product: dict | None
    counter_argument: str
    brazil_note: str


def load_hardware_db(path: str | pathlib.Path | None = None) -> dict:
    p = pathlib.Path(path) if path else DEFAULT_DB_PATH
    if not p.exists():
        return {"wheelbases": [], "pedals": []}
    with open(p, "r") as f:
        data = yaml.safe_load(f)
    return data or {"wheelbases": [], "pedals": []}


def _filter_by_brand(items: list[dict], brand: str | None) -> list[dict]:
    if not brand or brand.lower() == "any":
        return items
    return [i for i in items if i.get("brand", "").lower() == brand.lower()]


def recommend_hardware(
    weaknesses: list[Weakness],
    hardware: HardwareInfo,
    budget_usd: float,
    brand_constraint: str | None = None,
    db_path: str | pathlib.Path | None = None,
) -> list[HardwareRecommendation]:
    db = load_hardware_db(db_path)
    recs: list[HardwareRecommendation] = []

    for w in weaknesses:
        if w.root_cause != RootCause.HARDWARE:
            recs.append(HardwareRecommendation(
                weakness_key=w.key,
                verdict="no_upgrade_needed",
                summary=(
                    f"'{w.name}' is classified as {w.root_cause.value}, not hardware-limited. "
                    f"Current hardware ({hardware.wheel_model}, {hardware.pedals_model}) is not the bottleneck."
                ),
                product=None,
                counter_argument="None — no upgrade indicated.",
                brazil_note="",
            ))
            continue

        if budget_usd <= 0:
            recs.append(HardwareRecommendation(
                weakness_key=w.key,
                verdict="no_upgrade_needed",
                summary=(
                    f"'{w.name}' is hardware-limited but user has no budget for upgrade. "
                    "Mitigate via settings tuning and technique drills below."
                ),
                product=None,
                counter_argument="None — user constraint.",
                brazil_note="",
            ))
            continue

        # Find candidate products that address this weakness key
        if w.key in ("brake_cv", "brake_rate"):
            pool = _filter_by_brand(db.get("pedals", []), brand_constraint)
        elif w.key in ("steering_jitter",):
            pool = _filter_by_brand(db.get("wheelbases", []), brand_constraint)
        else:
            pool = []
        candidates = [p for p in pool if w.key in (p.get("recommended_for") or [])]
        candidates = [p for p in candidates if p.get("price_usd", 0) <= budget_usd]
        # exclude current hardware
        candidates = [
            p for p in candidates
            if p["name"].lower() not in (hardware.wheel_model.lower(), hardware.pedals_model.lower())
        ]
        # ensure recommended hardware *exceeds* current spec
        if w.key == "steering_jitter":
            candidates = [p for p in candidates if p.get("torque_nm", 0) > hardware.wheel_torque_nm]
        if w.key in ("brake_cv", "brake_rate"):
            type_order = {"potentiometer": 0, "hall_effect": 1, "load_cell": 2, "hydraulic": 3, "unknown": -1}
            current_rank = type_order.get(hardware.pedals_type, -1)
            candidates = [p for p in candidates if type_order.get(p.get("type", "unknown"), -1) > current_rank]

        if not candidates:
            recs.append(HardwareRecommendation(
                weakness_key=w.key,
                verdict="no_upgrade_needed",
                summary=(
                    f"No product in the database (brand={brand_constraint}, budget=${budget_usd:.0f}) "
                    "meaningfully upgrades the user's current hardware for this weakness."
                ),
                product=None,
                counter_argument="None.",
                brazil_note="",
            ))
            continue

        candidates.sort(key=lambda p: p.get("price_usd", 0))
        chosen = candidates[0]
        recs.append(HardwareRecommendation(
            weakness_key=w.key,
            verdict="upgrade_recommended",
            summary=f"For '{w.name}': consider {chosen['name']} (${chosen.get('price_usd')})",
            product=chosen,
            counter_argument=(
                f"Counter-argument: telemetry could improve from technique alone before the upgrade is "
                f"justified. Validate by drilling the practice plan first; if {w.key} persists after "
                "10 hours of focused practice, then upgrade."
            ),
            brazil_note=chosen.get("import_duty_note", ""),
        ))
    return recs
