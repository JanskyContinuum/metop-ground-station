import sys
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from groundstation.hardware.sdr import SDRReceiver


class Device:
    def __init__(self, code=4):
        self.code = code
        self.calls = []
        self.closed = False

    def setSampleRate(self, *args):
        self.calls.append(("rate", args[-1]))

    def getSampleRate(self, *args):
        return 6000000

    def setFrequency(self, *args):
        self.calls.append(("frequency", args[-1]))

    def setGainMode(self, *args):
        self.calls.append(("agc", args[-1]))

    def setGain(self, *args):
        self.calls.append(("gain", args[-1]))

    def getSettingInfo(self, *args):
        return [SimpleNamespace(key="biastee")]

    def writeSetting(self, *args):
        self.calls.append(("biastee", args[-1]))

    def getHardwareInfo(self):
        return {"model": "test"}

    def setupStream(self, *args):
        return object()

    def getStreamMTU(self, *args):
        return 4

    def activateStream(self, *args):
        return 0

    def readStream(self, stream, buffers, mtu, **kwargs):
        assert mtu == 4 and buffers[0].dtype == np.int16
        buffers[0][:] = [1, 2] * 4
        return SimpleNamespace(ret=self.code)

    def deactivateStream(self, *args):
        self.calls.append(("deactivate", True))

    def closeStream(self, *args):
        self.closed = True


def install(monkeypatch, device):
    monkeypatch.setitem(
        sys.modules,
        "SoapySDR",
        SimpleNamespace(
            Device=lambda args: device, SOAPY_SDR_RX=0, SOAPY_SDR_CS16="CS16", SOAPY_SDR_TIMEOUT=-1
        ),
    )


def test_sdr_actual_rate_manual_gain_and_mtu(config, tmp_path, monkeypatch):
    device = Device()
    install(monkeypatch, device)
    with SDRReceiver(config.sdr) as receiver:
        assert receiver.actual_rate == 6000000
        result = receiver.record(tmp_path / "iq.cs16", 0.01, threading.Event())
    assert ("agc", False) in device.calls
    assert ("biastee", "false") in device.calls
    assert (tmp_path / "iq.cs16").stat().st_size == result["samples"] * 4
    assert device.closed


def test_stream_error_closes_resources(config, tmp_path, monkeypatch):
    device = Device(-4)
    install(monkeypatch, device)
    with SDRReceiver(config.sdr) as receiver:
        with pytest.raises(RuntimeError, match="data loss"):
            receiver.record(tmp_path / "iq.cs16", 1, threading.Event())
    assert device.closed


def test_timeouts_are_bounded(config, tmp_path, monkeypatch):
    device = Device(-1)
    install(monkeypatch, device)
    config.sdr.stall_timeout_sec = 0.01
    with SDRReceiver(config.sdr) as receiver:
        with pytest.raises(TimeoutError):
            receiver.record(tmp_path / "iq.cs16", 1, threading.Event())
    assert device.closed


def test_power_integrates_without_integer_overflow(config, monkeypatch):
    receiver = SDRReceiver(config.sdr)
    monkeypatch.setattr(
        receiver, "chunks", lambda *args: iter([np.array([16000, 16000] * 4, dtype=np.int16)])
    )
    assert receiver.mean_power(1, threading.Event()) == pytest.approx(2 * (16000 / 32768) ** 2)
