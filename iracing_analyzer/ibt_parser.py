"""Parse iRacing .ibt binary telemetry files via pyirsdk.

Handles both raw .ibt files and .ibt.zip archives. Reports channel
inventory before analysis and degrades gracefully when optional
channels are missing.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Any

try:
    import irsdk  # pyirsdk on PyPI
except ImportError as e:
    raise ImportError(
        "pyirsdk is required. Install with: pip install pyirsdk"
    ) from e


REQUIRED_CHANNELS = ["Speed", "Brake", "Throttle", "Lap"]
OPTIONAL_CHANNELS = [
    "SteeringWheelAngle",
    "SteeringWheelTorque",
    "LateralAccel",
    "LongitudinalAccel",
    "LapDist",
    "LapDistPct",
    "OnPitRoad",
    "LapLastLapTime",
    "LapCurrentLapTime",
    "BrakeRaw",
    "ThrottleRaw",
    "Gear",
    "RPM",
    "SessionTime",
]


@dataclass
class ChannelMeta:
    name: str
    unit: str
    description: str
    dtype: str


@dataclass
class ParsedSession:
    channels_available: list[str]
    missing_channels: list[str]
    channel_meta: dict[str, ChannelMeta]
    session_info: dict
    weekend_info: dict
    total_samples: int
    sample_rate_hz: float
    data: dict[str, list] = field(default_factory=dict)
    source_path: str = ""

    def has(self, channel: str) -> bool:
        return channel in self.data and self.data[channel] is not None

    def get(self, channel: str, default=None):
        return self.data.get(channel, default)


def _extract_zip_if_needed(path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path | None]:
    """If path is a .zip, extract the first .ibt to a temp dir.

    Returns (ibt_path, temp_dir_to_cleanup_or_None).
    """
    if path.suffix.lower() != ".zip":
        return path, None
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="ibt_extract_"))
    with zipfile.ZipFile(path, "r") as zf:
        ibt_members = [n for n in zf.namelist() if n.lower().endswith(".ibt")]
        if not ibt_members:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise ValueError(f"No .ibt file found inside zip: {path}")
        zf.extract(ibt_members[0], tmpdir)
        return tmpdir / ibt_members[0], tmpdir


def open_ibt(path: str | pathlib.Path) -> tuple[Any, pathlib.Path | None]:
    """Open a .ibt or .ibt.zip file. Returns (irsdk_instance, temp_dir_or_None).

    Caller is responsible for shutil.rmtree(temp_dir) when done if non-None.
    """
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"IBT file not found: {p}")
    ibt_path, tmpdir = _extract_zip_if_needed(p)
    ir = irsdk.IRSDK()
    ok = ir.startup(test_file=str(ibt_path))
    if not ok:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
        raise RuntimeError(f"irsdk failed to open file: {ibt_path}")
    return ir, tmpdir


def enumerate_channels(ir: Any, print_table: bool = True) -> list[ChannelMeta]:
    """Read all channel metadata and optionally print a table to stdout."""
    metas: list[ChannelMeta] = []
    names = list(getattr(ir, "var_headers_names", []) or [])
    headers = getattr(ir, "_var_headers_dict", {}) or {}
    for name in names:
        vh = headers.get(name)
        unit = getattr(vh, "unit", "") if vh else ""
        desc = getattr(vh, "desc", "") if vh else ""
        type_code = getattr(vh, "type", None) if vh else None
        dtype = _type_code_to_str(type_code)
        metas.append(ChannelMeta(name=name, unit=unit or "", description=desc or "", dtype=dtype))
    if print_table:
        print(f"\n{'Channel':30s} {'Unit':15s} {'Type':8s} Description")
        print("-" * 90)
        for m in metas:
            print(f"{m.name:30s} {m.unit:15s} {m.dtype:8s} {m.description}")
        print(f"\nTotal channels: {len(metas)}\n")
    return metas


def _type_code_to_str(code) -> str:
    mapping = {0: "char", 1: "bool", 2: "int", 3: "bitfield", 4: "float", 5: "double"}
    try:
        return mapping.get(int(code), "?")
    except (TypeError, ValueError):
        return "?"


def _safe_get_all(ir: Any, name: str) -> list | None:
    """Call ir.get_all(name) defensively; return None on any failure."""
    try:
        data = ir.get_all(name)
        if data is None:
            return None
        return list(data)
    except Exception:
        return None


def _detect_sample_rate(ir: Any) -> float:
    """Read tick_rate from disk header; fall back to 60 Hz."""
    for attr_path in ["_disk_header.tick_rate", "_header.tick_rate"]:
        obj = ir
        try:
            for part in attr_path.split("."):
                obj = getattr(obj, part)
            if obj and isinstance(obj, (int, float)) and obj > 0:
                return float(obj)
        except AttributeError:
            continue
    return 60.0


def _detect_total_samples(ir: Any, fallback_channel: str = "SessionTime") -> int:
    """Try disk_header.session_record_count; fall back to channel length."""
    try:
        dh = getattr(ir, "_disk_header", None)
        n = getattr(dh, "session_record_count", None) if dh else None
        if n and int(n) > 0:
            return int(n)
    except Exception:
        pass
    data = _safe_get_all(ir, fallback_channel)
    return len(data) if data else 0


def _extract_info_dict(ir: Any, key: str) -> dict:
    """Extract a top-level YAML section from session info; never raise."""
    try:
        val = ir[key]
        if isinstance(val, dict):
            return val
    except Exception:
        pass
    return {}


def load_session(
    path: str | pathlib.Path,
    required: list[str] | None = None,
    optional: list[str] | None = None,
    print_inventory: bool = True,
) -> ParsedSession:
    """Open file, enumerate channels, bulk-load required + optional.

    Required-channel absence raises ValueError; optional absences populate
    `missing_channels` so the report can flag them.
    """
    required = required or REQUIRED_CHANNELS
    optional = optional or OPTIONAL_CHANNELS
    ir, tmpdir = open_ibt(path)
    try:
        metas = enumerate_channels(ir, print_table=print_inventory)
        available_names = {m.name for m in metas}
        missing_required = [c for c in required if c not in available_names]
        if missing_required:
            raise ValueError(
                f"Required channels missing from .ibt: {missing_required}. "
                f"Analysis cannot proceed."
            )

        data: dict[str, list] = {}
        for ch in required:
            arr = _safe_get_all(ir, ch)
            if arr is None:
                raise ValueError(f"Channel {ch} listed but unreadable")
            data[ch] = arr

        missing_optional: list[str] = []
        for ch in optional:
            if ch in available_names:
                arr = _safe_get_all(ir, ch)
                if arr is None:
                    missing_optional.append(ch)
                else:
                    data[ch] = arr
            else:
                missing_optional.append(ch)

        sample_rate = _detect_sample_rate(ir)
        total = _detect_total_samples(ir)
        if total == 0 and data.get("Speed"):
            total = len(data["Speed"])

        weekend = _extract_info_dict(ir, "WeekendInfo")
        session_info = _extract_info_dict(ir, "SessionInfo")

        return ParsedSession(
            channels_available=sorted(available_names),
            missing_channels=missing_optional,
            channel_meta={m.name: m for m in metas},
            session_info=session_info,
            weekend_info=weekend,
            total_samples=total,
            sample_rate_hz=sample_rate,
            data=data,
            source_path=str(path),
        )
    finally:
        try:
            ir.shutdown()
        except Exception:
            pass
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
