import math
import socket
import threading
import time


def legal_azimuth(azimuth, current, config):
    if not math.isfinite(azimuth) or not math.isfinite(current):
        raise ValueError("Non-finite rotor position")
    azimuth %= 360
    first = math.ceil((config.azimuth_min_deg - azimuth) / 360)
    last = math.floor((config.azimuth_max_deg - azimuth) / 360)
    choices = [azimuth + 360 * k for k in range(first, last + 1)]
    if not choices:
        raise ValueError("Azimuth is outside mechanical range")
    return min(choices, key=lambda a: abs(a - current))


class RotorController:
    def __init__(self, config):
        self.config = config
        self.mutex = threading.RLock()

    def _request(self, command, lines=1):
        if not self.config.host:
            raise ValueError("Set rotor.host to the verified Pi Zero address")
        with socket.create_connection(
            (self.config.host, self.config.port), timeout=self.config.timeout_sec
        ) as sock:
            sock.settimeout(self.config.timeout_sec)
            sock.sendall((command + "\n").encode("ascii"))
            with sock.makefile("rb") as stream:
                result = []
                for _ in range(lines):
                    line = stream.readline(256).decode("ascii").strip()
                    if not line or len(line) >= 255:
                        raise RuntimeError("Incomplete rotctld response")
                    if line.startswith("RPRT") and line != "RPRT 0":
                        raise RuntimeError(f"rotctld rejected command: {line}")
                    result.append(line)
                return result

    def get_position(self):
        with self.mutex:
            result = tuple(map(float, self._request("p", 2)))
            if not all(math.isfinite(n) for n in result):
                raise RuntimeError("Non-finite rotctld position")
            return result

    def set_position(self, azimuth, elevation):
        with self.mutex:
            if not self.config.limits_confirmed:
                raise ValueError(
                    "Confirm rotor mechanical limits and clear swept paths in configuration"
                )
            if not math.isfinite(elevation) or not (
                self.config.elevation_min_deg <= elevation <= self.config.elevation_max_deg
            ):
                raise ValueError("Elevation outside mechanical range")
            current, _ = self.get_position()
            target = legal_azimuth(azimuth, current, self.config)
            if self._request(f"P {target:.3f} {elevation:.3f}") != ["RPRT 0"]:
                raise RuntimeError("Unexpected rotctld acknowledgement")
            return target, elevation

    def stop(self):
        with self.mutex:
            if self._request("S") != ["RPRT 0"]:
                raise RuntimeError("rotctld STOP was not acknowledged")

    def park(self):
        return self.set_position(self.config.park_azimuth_deg, self.config.park_elevation_deg)

    def healthcheck(self):
        return self.get_position()

    def wait_for_position(self, target, stop):
        deadline = time.monotonic() + self.config.settle_timeout_sec
        while not stop.is_set():
            actual = self.get_position()
            if all(
                abs(a - b) <= self.config.position_tolerance_deg for a, b in zip(actual, target)
            ):
                return
            if time.monotonic() >= deadline:
                raise TimeoutError("Rotor did not reach commanded position")
            stop.wait(0.3)
        raise InterruptedError("Pointing cancelled")
