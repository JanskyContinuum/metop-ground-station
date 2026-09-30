import io

import pytest

from groundstation.hardware.rotor import RotorController, legal_azimuth


def test_nearest_legal_azimuth(config):
    assert legal_azimuth(350, 0, config.rotor) == -10
    assert legal_azimuth(270, -100, config.rotor) == -90
    assert legal_azimuth(-90, 280, config.rotor) == 270
    config.rotor.azimuth_min_deg = 20
    config.rotor.azimuth_max_deg = 100
    with pytest.raises(ValueError):
        legal_azimuth(200, 30, config.rotor)


def test_invalid_elevation_never_sends_command(config, monkeypatch):
    config.rotor.limits_confirmed = True
    rotor = RotorController(config.rotor)
    monkeypatch.setattr(rotor, "_request", lambda *_: pytest.fail("unsafe command sent"))
    for elevation in (0, 181, float("nan")):
        with pytest.raises(ValueError):
            rotor.set_position(0, elevation)


def test_unconfirmed_limits_reject_motion(config):
    with pytest.raises(ValueError, match="Confirm"):
        RotorController(config.rotor).set_position(0, 60)


def test_rotctld_reads_separate_lines_and_exact_ack(config, monkeypatch):
    import socket

    responses = iter([b"12.5\n60.0\n", b"12.5\n60.0\n", b"RPRT 0\n", b"RPRT -1\n"])
    sent = []

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def settimeout(self, timeout):
            assert timeout > 0

        def sendall(self, data):
            sent.append(data)

        def makefile(self, *_):
            return io.BytesIO(next(responses))

    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: Socket())
    config.rotor.host = "test.invalid"
    config.rotor.limits_confirmed = True
    rotor = RotorController(config.rotor)
    assert rotor.get_position() == (12.5, 60)
    assert rotor.set_position(350, 60) == (-10, 60)
    assert sent[-1] == b"P -10.000 60.000\n"
    with pytest.raises(RuntimeError):
        rotor.stop()
