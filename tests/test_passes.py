from datetime import UTC, datetime, timedelta

import pytest

from groundstation.orbit.horizon import HorizonMask
from groundstation.orbit.passes import orbital_time, predict, visibility_windows
from groundstation.orbit.tle import parse_tle


def test_prediction_real_pyorbital(config, tle_text):
    records = parse_tle(tle_text)
    now = next(iter(records.values())).epoch
    config.passes.prediction_hours = 24
    config.passes.minimum_max_elevation_deg = 0
    config.rotor.elevation_min_deg = 0
    config.horizon_mask = [(0, 0)]
    passes = predict(config, records, now)
    assert passes
    assert all(p.aos.tzinfo is UTC and p.los > now for p in passes)
    assert all(p.aos <= now + timedelta(hours=24) for p in passes)
    assert all(0 < p.usable_duration <= p.duration for p in passes)
    config.passes.minimum_max_elevation_deg = 90
    assert predict(config, records, now) == []


def test_visibility_does_not_bridge_obstruction(config):
    start = datetime(2026, 1, 1, tzinfo=UTC)

    def position(t):
        return 120, 0 if 4 <= (t - start).total_seconds() <= 6 else 65

    windows = visibility_windows(
        start, start + timedelta(seconds=10), position, HorizonMask([(0, 30)]), config.rotor, 1
    )
    assert [
        (int((a - start).total_seconds()), int((b - start).total_seconds())) for a, b in windows
    ] == [(0, 3), (7, 10)]


def test_naive_time_rejected():
    with pytest.raises(ValueError):
        orbital_time(datetime(2026, 1, 1))
