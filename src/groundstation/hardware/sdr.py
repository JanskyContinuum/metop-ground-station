import math
import time
from datetime import UTC, datetime

import numpy as np


class SDRReceiver:
    """Lazy SoapySDR import keeps mock mode and tests independent of native drivers."""

    def __init__(self, config):
        self.config = config
        self.device = None
        self.stream = None
        self.actual_rate = None

    def __enter__(self):
        import SoapySDR

        self.api = SoapySDR
        self.device = SoapySDR.Device(dict(driver=self.config.driver))
        try:
            rx = SoapySDR.SOAPY_SDR_RX
            self.device.setSampleRate(rx, 0, self.config.sample_rate_hz)
            self.actual_rate = float(self.device.getSampleRate(rx, 0))
            if not math.isfinite(self.actual_rate) or self.actual_rate <= 0:
                raise RuntimeError("SDR returned invalid actual sample rate")
            self.device.setFrequency(rx, 0, self.config.center_frequency_hz)
            self.device.setGainMode(rx, 0, self.config.agc)
            if not self.config.agc:
                self.device.setGain(rx, 0, self.config.gain)
            # SDRplay plugins differ in channel/global setting scope. Discover explicitly.
            global_keys = {item.key for item in self.device.getSettingInfo()}
            channel_keys = {item.key for item in self.device.getSettingInfo(rx, 0)}
            value = str(self.config.biastee).lower()
            if "biastee" in channel_keys:
                self.device.writeSetting(rx, 0, "biastee", value)
            elif "biastee" in global_keys:
                self.device.writeSetting("biastee", value)
            else:
                raise RuntimeError(
                    "Driver exposes no biastee setting; verify the installed Soapy plugin"
                )
            return self
        except Exception:
            self.close()
            raise

    def info(self):
        return dict(
            hardware=dict(self.device.getHardwareInfo()),
            requested_sample_rate_hz=self.config.sample_rate_hz,
            actual_sample_rate_hz=self.actual_rate,
        )

    def chunks(self, seconds, stop):
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Acquisition duration must be positive")
        api = self.api
        self.stream = self.device.setupStream(api.SOAPY_SDR_RX, api.SOAPY_SDR_CS16, [0])
        try:
            mtu = self.device.getStreamMTU(self.stream)
            if mtu <= 0:
                raise RuntimeError("Invalid SDR stream MTU")
            buffer = np.empty(mtu * 2, dtype=np.int16)
            result = self.device.activateStream(self.stream)
            if result != 0:
                raise RuntimeError(f"SDR stream activation failed: {result}")
            deadline = time.monotonic() + seconds
            last_data = time.monotonic()
            while not stop.is_set() and time.monotonic() < deadline:
                result = self.device.readStream(self.stream, [buffer], mtu, timeoutUs=200000)
                if result.ret > 0:
                    last_data = time.monotonic()
                    yield buffer[: result.ret * 2]
                elif result.ret not in (0, api.SOAPY_SDR_TIMEOUT):
                    # Overflow is data loss, not a timeout that may be silently ignored.
                    raise RuntimeError(f"SDR stream failure/data loss: {result.ret}")
                if time.monotonic() - last_data > self.config.stall_timeout_sec:
                    raise TimeoutError("SDR stopped providing samples")
        finally:
            self._close_stream()

    def record(self, path, seconds, stop):
        started = datetime.now(UTC)
        samples = 0
        with path.open("xb") as output:
            for chunk in self.chunks(seconds, stop):
                output.write(chunk.astype("<i2", copy=False).tobytes())
                samples += chunk.size // 2
        if not samples:
            raise RuntimeError("No SDR samples received")
        return dict(
            recording_start=started.isoformat(),
            recording_end=datetime.now(UTC).isoformat(),
            samples=samples,
            actual_sample_rate_hz=self.actual_rate,
        )

    def mean_power(self, seconds, stop):
        total, count, clipped = 0.0, 0, 0
        for chunk in self.chunks(seconds, stop):
            values = chunk.astype(np.float64) / 32768
            clipped += np.count_nonzero(np.abs(values) >= 0.999)
            total += float(np.dot(values, values))
            count += chunk.size // 2
        if stop.is_set():
            raise InterruptedError("Power integration cancelled")
        if not count or total <= 0:
            raise RuntimeError("No valid power samples")
        if clipped:
            raise RuntimeError("ADC clipping detected; reduce manual gain before G/T measurement")
        return total / count

    def _close_stream(self):
        if self.stream is not None:
            try:
                self.device.deactivateStream(self.stream)
            finally:
                self.device.closeStream(self.stream)
                self.stream = None

    def close(self):
        try:
            self._close_stream()
        finally:
            self.device = None

    def __exit__(self, *_):
        self.close()
