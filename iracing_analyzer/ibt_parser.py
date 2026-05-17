"""Parse iRacing .ibt binary telemetry files via pyirsdk.IBT.

Handles both raw .ibt files and .ibt.zip archives. Reports channel
inventory before analysis and degrades gracefully when optional
channels are missing.
"""
from __future__ import annotations

import pathlib
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Any

try:
    import irsdk
except ImportError as e:
    raise ImportError("pyirsdk is required. Install with: pip install pyirsdk") from e

try:
    import yaml as _yaml
except ImportError:
    _yaml = None


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
    if path.suffix.lower() != ".zip":
        return path, None
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="ibt_extract_"))
    with zipfile.ZipFile(path, "r") as zf:
        ibt_members = [n for n in zf.namelist()
                       if n.lower().endswith(".ibt") and not n.startswith("__MACOSX")]
        if not ibt_members:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise ValueError(f"No .ibt file found inside zip: {path}")
        zf.extract(ibt_members[0], tmpdir)
        extracted = tmpdir / ibt_members[0]
        return extracted, tmpdir


def _open_ibt(path: pathlib.Path) -> irsdk.IBT:
    ibt = irsdk.IBT()
    ibt.open(str(path))
    if not ibt._header:
        raise RuntimeError(f"irsdk.IBT failed to open: {path}")
    return ibt


def _type_code_to_str(code) -> str:
    mapping = {0: "char", 1: "bool", 2: "int", 3: "bitfield", 4: "float", 5: "double"}
    try:
        return mapping.get(int(code), "?")
    except (TypeError, ValueError):
        return "?"


def enumerate_channels(ibt: irsdk.IBT, print_table: bool = True) -> list[ChannelMeta]:
    names = list(ibt.var_headers_names or [])
    hdict = ibt._var_headers_dict or {}
    metas: list[ChannelMeta] = []
    for name in names:
        vh = hdict.get(name)
        unit = getattr(vh, "unit", "") or ""
        desc = getattr(vh, "desc", "") or ""
        dtype = _type_code_to_str(getattr(vh, "type", None))
        metas.append(ChannelMeta(name=name, unit=unit, description=desc, dtype=dtype))
    if print_table:
        print(f"\n{'Channel':30s} {'Unit':15s} {'Type':8s} Description")
        print("-" * 90)
        for m in metas:
            print(f"{m.name:30s} {m.unit:15s} {m.dtype:8s} {m.description}")
        print(f"\nTotal channels: {len(metas)}\n")
    return metas


def _read_session_yaml(ibt: irsdk.IBT) -> dict:
    """Extract and parse the YAML session info block from the IBT header."""
    try:
        h = ibt._header
        mem = ibt._shared_mem
        offset = h.session_info_offset
        length = h.session_info_len
        raw = mem[offset: offset + length]
        text = raw.rstrip(b"\x00").decode("utf-8", errors="replace")
        if _yaml:
            return _yaml.safe_load(text) or {}
        return {}
    except Exception:
        return {}


def _safe_get_all(ibt: irsdk.IBT, name: str) -> list | None:
    try:
        data = ibt.get_all(name)
        return list(data) if data is not None else None
    except Exception:
        return None


def load_session(
    path: str | pathlib.Path,
    required: list[str] | None = None,
    optional: list[str] | None = None,
    print_inventory: bool = True,
) -> ParsedSession:
    required = required or REQUIRED_CHANNELS
    optional = optional or OPTIONAL_CHANNELS
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"IBT file not found: {p}")

    ibt_path, tmpdir = _extract_zip_if_needed(p)
    ibt = _open_ibt(ibt_path)
    try:
        metas = enumerate_channels(ibt, print_table=print_inventory)
        available_names = {m.name for m in metas}

        missing_required = [c for c in required if c not in available_names]
        if missing_required:
            raise ValueError(
                f"Required channels missing: {missing_required}. Analysis cannot proceed."
            )

        data: dict[str, list] = {}
        for ch in required:
            arr = _safe_get_all(ibt, ch)
            if arr is None:
                raise ValueError(f"Required channel '{ch}' listed but unreadable")
            data[ch] = arr

        missing_optional: list[str] = []
        for ch in optional:
            if ch in available_names:
                arr = _safe_get_all(ibt, ch)
                if arr is None:
                    missing_optional.append(ch)
                else:
                    data[ch] = arr
            else:
                missing_optional.append(ch)

        sample_rate = float(ibt._header.tick_rate) if ibt._header.tick_rate else 60.0
        total = int(ibt._disk_header.session_record_count) if ibt._disk_header else 0
        if total == 0 and data.get("Speed"):
            total = len(data["Speed"])

        session_yaml = _read_session_yaml(ibt)
        weekend_info = session_yaml.get("WeekendInfo", {}) or {}
        session_info = session_yaml.get("SessionInfo", {}) or {}

        return ParsedSession(
            channels_available=sorted(available_names),
            missing_channels=missing_optional,
            channel_meta={m.name: m for m in metas},
            session_info=session_info,
            weekend_info=weekend_info,
            total_samples=total,
            sample_rate_hz=sample_rate,
            data=data,
            source_path=str(path),
        )
    finally:
        try:
            ibt.close()
        except Exception:
            pass
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
