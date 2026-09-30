import os
import time

import httpx
import pytest

from groundstation.orbit.tle import TLEManager, parse_tle


def test_valid_cache_freshness_and_rate_limit(config, tle_text):
    calls = []
    manager = TLEManager(config.tle, config.storage.root, lambda url: calls.append(url) or tle_text)
    assert len(manager.load()) == 2
    assert manager.age_hours() < 0.1
    manager.load()
    manager.load(force=True)
    assert len(calls) == 1
    assert "FORMAT=TLE" in calls[0]


def test_stale_cache_survives_offline_and_invalid_download(config, tle_text):
    manager = TLEManager(config.tle, config.storage.root, lambda _: tle_text)
    manager.load()
    original = manager.path.read_bytes()
    os.utime(manager.path, (time.time() - 100000,) * 2)
    for fail in (
        lambda _: "<html>upstream error</html>",
        lambda _: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    ):
        manager.fetch = fail
        manager.last_attempt = -float("inf")
        assert len(manager.load()) == 2
        assert manager.warning
        assert manager.path.read_bytes() == original


def test_missing_offline_cache_is_recoverable(config):
    manager = TLEManager(
        config.tle,
        config.storage.root,
        lambda _: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )
    assert manager.load() == {}
    assert "no passes" in manager.warning


def test_bad_checksum_rejected(tle_text):
    with pytest.raises(ValueError):
        parse_tle(tle_text.replace("1 ", "1X", 1))


def test_corrupt_fresh_cache_refreshed(config, tle_text):
    manager = TLEManager(config.tle, config.storage.root, lambda _: tle_text)
    manager.load()
    manager.path.write_text("corrupt")
    manager.last_attempt = -float("inf")
    assert len(manager.load()) == 2
    assert len(parse_tle(manager.path.read_text())) == 2
