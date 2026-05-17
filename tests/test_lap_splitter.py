"""Unit tests for lap splitting and reference-lap selection."""
from iracing_analyzer.ibt_parser import ChannelMeta, ParsedSession
from iracing_analyzer.lap_splitter import find_reference_lap, split_laps


def _session(lap_channel, speed=None, on_pit=None, lap_last=None, rate=60.0):
    n = len(lap_channel)
    data = {
        "Lap": lap_channel,
        "Speed": speed if speed is not None else [40.0] * n,
        "Brake": [0.0] * n,
        "Throttle": [1.0] * n,
    }
    if on_pit is not None:
        data["OnPitRoad"] = on_pit
    if lap_last is not None:
        data["LapLastLapTime"] = lap_last
    return ParsedSession(
        channels_available=list(data.keys()),
        missing_channels=[],
        channel_meta={k: ChannelMeta(k, "", "", "float") for k in data},
        session_info={},
        weekend_info={},
        total_samples=n,
        sample_rate_hz=rate,
        data=data,
    )


def test_split_three_laps():
    rate = 60.0
    n = int(60 * rate)
    lap_ch = [1] * n + [2] * n + [3] * n
    sess = _session(lap_ch, rate=rate)
    laps = split_laps(sess)
    assert len(laps) == 3
    assert [l.lap_number for l in laps] == [1, 2, 3]


def test_pit_lap_marked_invalid():
    rate = 60.0
    n = int(60 * rate)
    lap_ch = [1] * n + [2] * n
    on_pit = [False] * n + [True] * n
    sess = _session(lap_ch, on_pit=on_pit, rate=rate)
    laps = split_laps(sess)
    assert laps[0].is_valid
    assert not laps[1].is_valid


def test_short_lap_invalid():
    rate = 60.0
    n = int(60 * rate)
    short = int(20 * rate)
    lap_ch = [1] * short + [2] * n
    sess = _session(lap_ch, rate=rate)
    laps = split_laps(sess)
    assert not laps[0].is_valid
    assert laps[1].is_valid


def test_find_reference_lap_picks_fastest():
    rate = 60.0
    n = int(90 * rate)
    lap_ch = [1] * n + [2] * n + [3] * n
    # LapLastLapTime populated at the *start* of the next lap
    lap_last = [0.0] * n + [95.0] * n + [88.0] * n
    sess = _session(lap_ch, lap_last=lap_last, rate=rate)
    laps = split_laps(sess)
    ref = find_reference_lap(laps)
    assert ref is not None
    # second lap (recorded as 88s at the start of lap 3) should be fastest
    assert ref.lap_number == 2
