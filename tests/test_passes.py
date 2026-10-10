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
    # This orbital/time-range test deliberately admits low and eastern passes.
    config.tracking_limits.start_azimuth_gt_deg = 0
    config.tracking_limits.start_elevation_gt_deg = 1
    config.tracking_limits.stop_elevation_deg = 0
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


def test_tracking_start_stop_and_no_restart(config):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    config.rotor.elevation_min_deg = 0
    points = [
        (200, 60),
        (201, 50),
        (201, 51),
        (180, 40),
        (180, 21),
        (180, 20),
        (240, 65),
        (240, 65),
    ]
    windows = visibility_windows(
        start,
        start + timedelta(seconds=7),
        lambda t: points[int((t - start).total_seconds())],
        HorizonMask([(0, 0)]),
        config.rotor,
        1,
        config.tracking_limits,
    )
    assert windows == ((start + timedelta(seconds=2), start + timedelta(seconds=4)),)


def test_existing_floor_and_mask_still_cut_tracking_window(config):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    points = [(240, 65), (240, 55), (240, 45), (240, 30)]

    def position(t):
        return points[int((t - start).total_seconds())]

    for floor, mask in [(50, 0), (0, 50)]:
        config.rotor.elevation_min_deg = floor
        windows = visibility_windows(
            start,
            start + timedelta(seconds=3),
            position,
            HorizonMask([(0, mask)]),
            config.rotor,
            1,
            config.tracking_limits,
        )
        assert windows == ((start, start + timedelta(seconds=1)),)


def test_mechanical_sector_is_used_by_prediction(config):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    config.rotor.elevation_min_deg = 0
    assert not visibility_windows(
        start,
        start + timedelta(seconds=5),
        lambda t: (200, 9),
        HorizonMask([(0, 0)]),
        config.rotor,
        1,
    )
