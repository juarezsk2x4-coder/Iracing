"""Split a ParsedSession into per-lap data slices and find the reference lap."""
from __future__ import annotations

from dataclasses import dataclass

from .ibt_parser import ParsedSession


MIN_VALID_LAP_SECONDS = 30.0
PIT_SPEED_MPS = 8.0


@dataclass
class LapData:
    lap_number: int
    start_sample: int
    end_sample: int
    lap_time_s: float | None
    is_valid: bool
    data: dict[str, list]
    sample_rate_hz: float

    @property
    def duration_s(self) -> float:
        return (self.end_sample - self.start_sample) / self.sample_rate_hz


def _slice_data(session: ParsedSession, start: int, end: int) -> dict[str, list]:
    out: dict[str, list] = {}
    for ch, arr in session.data.items():
        if arr is None:
            out[ch] = None
            continue
        out[ch] = arr[start:end]
    return out


def _lap_appears_pit(lap_data: dict[str, list]) -> bool:
    pit = lap_data.get("OnPitRoad")
    if pit:
        return any(bool(v) for v in pit)
    speed = lap_data.get("Speed") or []
    if not speed:
        return False
    # heuristic: if more than 40% of samples below pit speed, treat as pit lap
    below = sum(1 for v in speed if v is not None and v < PIT_SPEED_MPS)
    return below > 0.4 * len(speed)


def split_laps(session: ParsedSession) -> list[LapData]:
    """Detect lap boundaries via the `Lap` channel and slice each lap."""
    lap_ch = session.data.get("Lap")
    if not lap_ch:
        raise ValueError("Lap channel missing — cannot split laps")

    boundaries: list[int] = [0]
    prev = lap_ch[0]
    for i in range(1, len(lap_ch)):
        cur = lap_ch[i]
        if cur != prev:
            boundaries.append(i)
            prev = cur
    boundaries.append(len(lap_ch))

    laps: list[LapData] = []
    lap_last = session.data.get("LapLastLapTime")
    rate = session.sample_rate_hz

    for idx in range(len(boundaries) - 1):
        start = boundaries[idx]
        end = boundaries[idx + 1]
        if end - start < 2:
            continue
        lap_number = int(lap_ch[start]) if lap_ch[start] is not None else idx
        sliced = _slice_data(session, start, end)
        duration_s = (end - start) / rate

        lap_time: float | None = None
        if lap_last:
            # LapLastLapTime is populated at the start of the *next* lap. Look at
            # the first few samples of the next lap if available.
            next_start = boundaries[idx + 1] if idx + 1 < len(boundaries) - 1 else None
            if next_start is not None and next_start < len(lap_last):
                candidate = lap_last[next_start]
                if candidate and candidate > 0:
                    lap_time = float(candidate)
        if lap_time is None and duration_s >= MIN_VALID_LAP_SECONDS:
            lap_time = duration_s

        is_pit = _lap_appears_pit(sliced)
        is_valid = (
            not is_pit
            and duration_s >= MIN_VALID_LAP_SECONDS
            and lap_time is not None
            and lap_time >= MIN_VALID_LAP_SECONDS
        )

        laps.append(
            LapData(
                lap_number=lap_number,
                start_sample=start,
                end_sample=end,
                lap_time_s=lap_time,
                is_valid=is_valid,
                data=sliced,
                sample_rate_hz=rate,
            )
        )
    return laps


def find_reference_lap(laps: list[LapData]) -> LapData | None:
    """Return the valid lap with the lowest lap_time_s."""
    valid = [l for l in laps if l.is_valid and l.lap_time_s is not None]
    if not valid:
        return None
    return min(valid, key=lambda l: l.lap_time_s)
