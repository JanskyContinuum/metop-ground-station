import threading
from datetime import timedelta
from unittest.mock import Mock

import pytest

from groundstation.hardware.lock import HardwareBusy, HardwareLock
from groundstation.hardware.mocks import MockRotor, MockSatDump, MockSDR
from groundstation.orbit.passes import utcnow
from groundstation.services.cleanup import check_space, cleanup_failed, expected_bytes, remove_work
from groundstation.services.gallery import scan_gallery
from groundstation.services.observation import Observation


def observation(config, decoder=None):
    return Observation(
        config,
        MockRotor(config.rotor),
        MockSDR,
        decoder or MockSatDump(),
        HardwareLock(config.storage.root),
    )


def test_success_stores_image_then_cleans_all_work(config, quick_pass):
    states = []
    observation(config).execute(quick_pass, threading.Event(), states.append)
    assert states == ["PREPARING", "TRACKING", "PROCESSING", "COMPLETE"]
    gallery = scan_gallery(config.gallery_dir)
    assert len(gallery) == 1 and gallery[0]["simulated"]
    assert gallery[0]["actual_sample_rate_hz"] == config.sdr.sample_rate_hz
    assert not list(config.work_dir.iterdir())
    assert len(list(config.gallery_dir.rglob("*.*"))) == 2


def test_failed_decode_retains_raw_until_expiry(config, quick_pass):
    decoder = Mock()
    decoder.process.side_effect = RuntimeError("decoder failed")
    with pytest.raises(RuntimeError, match="decoder failed"):
        observation(config, decoder).execute(quick_pass, threading.Event(), lambda _: None)
    directory = next(config.work_dir.glob("obs-*"))
    assert (directory / "capture.cs16").stat().st_size > 0
    assert not scan_gallery(config.gallery_dir)
    assert not cleanup_failed(config.work_dir, 24)
    cleanup_failed(config.work_dir, 24, utcnow() + timedelta(hours=25))
    assert not directory.exists()


def test_gallery_write_failure_preserves_raw(config, quick_pass, monkeypatch):
    monkeypatch.setattr(
        "groundstation.services.observation.store_result", Mock(side_effect=OSError("disk full"))
    )
    with pytest.raises(OSError):
        observation(config).execute(quick_pass, threading.Event(), lambda _: None)
    assert list(config.work_dir.glob("obs-*/capture.cs16"))


def test_cancelled_observation_never_decodes(config, quick_pass):
    stop = threading.Event()
    stop.set()
    decoder = Mock()
    with pytest.raises(InterruptedError):
        observation(config, decoder).execute(quick_pass, stop, lambda _: None)
    decoder.process.assert_not_called()


def test_raw_size_and_free_space(config, tmp_path, monkeypatch):
    assert expected_bytes(5e6, 60) == 1_200_000_000
    monkeypatch.setattr("shutil.disk_usage", lambda _: type("Disk", (), {"free": 10})())
    with pytest.raises(RuntimeError, match="Insufficient disk"):
        check_space(tmp_path, 5e6, 60, config.storage)


def test_cleanup_scope_and_unmarked_files(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    unrelated = root / "other"
    unrelated.mkdir()
    (unrelated / "important.txt").write_text("keep")
    with pytest.raises(ValueError):
        remove_work(unrelated, root)
    with pytest.raises(ValueError):
        remove_work(root, root)
    cleanup_failed(root, 1, utcnow() + timedelta(days=100))
    assert (unrelated / "important.txt").exists()


def test_lock_prevents_other_threads_and_cli_instances(tmp_path):
    lock = HardwareLock(tmp_path)
    with lock.hold("tracking"):
        with pytest.raises(HardwareBusy):
            with lock.hold("SDR test"):
                pass
        with pytest.raises(HardwareBusy):
            with HardwareLock(tmp_path).hold("G/T CLI"):
                pass
    with lock.hold("released"):
        pass


def test_stop_prevents_late_motion(config):
    observer = observation(config)
    stop = threading.Event()
    observer.emergency_stop(stop)
    original = observer.rotor.get_position()
    with pytest.raises(InterruptedError):
        observer._point(130, 65, stop)
    assert observer.rotor.get_position() == original


def test_diagnostic_stop_is_latched(config):
    from groundstation.services.diagnostics import Diagnostics

    rotor = MockRotor(config.rotor)
    diagnostic = Diagnostics(
        config, rotor, MockSDR, MockSatDump(), HardwareLock(config.storage.root)
    )
    diagnostic.emergency_stop()
    with pytest.raises(InterruptedError):
        diagnostic.run("jog")
    assert rotor.stopped
