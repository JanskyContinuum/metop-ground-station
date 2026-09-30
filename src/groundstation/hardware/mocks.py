from datetime import UTC, datetime

from PIL import Image, ImageDraw

from groundstation.hardware.rotor import RotorController, legal_azimuth


class MockRotor(RotorController):
    def __init__(self, config):
        super().__init__(config)
        self.position = (config.park_azimuth_deg, config.park_elevation_deg)
        self.stopped = False

    def get_position(self):
        with self.mutex:
            return self.position

    def set_position(self, azimuth, elevation):
        with self.mutex:
            if not self.config.elevation_min_deg <= elevation <= self.config.elevation_max_deg:
                raise ValueError("Elevation outside mechanical range")
            self.position = legal_azimuth(azimuth, self.position[0], self.config), elevation
            self.stopped = False
            return self.position

    def stop(self):
        with self.mutex:
            self.stopped = True


class MockSDR:
    def __init__(self, config):
        self.config = config
        self.actual_rate = config.sample_rate_hz

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def info(self):
        return dict(
            hardware={"device": "SIMULATED RSP1B"},
            requested_sample_rate_hz=self.config.sample_rate_hz,
            actual_sample_rate_hz=self.actual_rate,
        )

    def record(self, path, seconds, stop):
        started = datetime.now(UTC)
        with path.open("xb") as stream:
            stream.write(b"\x01\x00\x02\x00" * 4096)
        stop.wait(max(0, seconds))
        return dict(
            recording_start=started.isoformat(),
            recording_end=datetime.now(UTC).isoformat(),
            samples=4096,
            actual_sample_rate_hz=self.actual_rate,
            mock=True,
        )

    def mean_power(self, seconds, stop):
        raise RuntimeError(
            "G/T requires real measured power; mock mode cannot produce a G/T result"
        )


class MockSatDump:
    def process(self, raw, output, rate, stop):
        if stop.is_set():
            raise InterruptedError("Processing cancelled")
        directory = output / "AVHRR"
        directory.mkdir(parents=True)
        image = Image.new("RGB", (800, 480), "#15394c")
        draw = ImageDraw.Draw(image)
        for i in range(14):
            draw.ellipse((i * 70 - 80, 100 + i % 3 * 40, i * 70 + 140, 350), fill="#789f9d")
        draw.rectangle((0, 0, 800, 70), fill="#102530")
        draw.text(
            (24, 25), "SIMULATED AVHRR - software demonstration, no RF reception", fill="white"
        )
        image.save(directory / "avhrr_composite.png")

    def available(self):
        return "SIMULATED SatDump"
