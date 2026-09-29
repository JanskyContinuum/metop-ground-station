import threading
import uuid

from groundstation.services.cleanup import check_space


class Diagnostics:
    def __init__(self, config, rotor, receiver_factory, decoder, lock, stop=None):
        self.config, self.rotor = config, rotor
        self.receiver_factory, self.decoder, self.lock = receiver_factory, decoder, lock
        self.stop = stop or threading.Event()
        self.status = {"rotor": "Not tested", "sdr": "Not tested", "satdump": "Not tested"}

    def run(self, action):
        with self.lock.hold(f"diagnostic {action}"):
            if self.stop.is_set():
                raise InterruptedError("Application is shutting down")
            if action in {"rotor", "position"}:
                result = self.rotor.healthcheck()
                self.status["rotor"] = f"Connected: az {result[0]:.1f}, el {result[1]:.1f}"
                return self.status["rotor"]
            if action == "park":
                target = self.rotor.park()
                self.rotor.wait_for_position(target, self.stop)
                return "Rotor parked"
            if action == "jog":
                original = self.rotor.get_position()
                target = original[0] + 2, original[1]
                if not self.config.rotor.azimuth_min_deg <= target[0] <= self.config.rotor.azimuth_max_deg:
                    target = original[0] - 2, original[1]
                try:
                    command = self.rotor.set_position(*target)
                    self.rotor.wait_for_position(command, self.stop)
                    command = self.rotor.set_position(*original)
                    self.rotor.wait_for_position(command, self.stop)
                    return "2 degree jog completed and original position restored"
                finally:
                    self.rotor.stop()
            if action == "stop":
                self.rotor.stop()
                return "Rotor STOP acknowledged"
            if action == "satdump":
                self.status["satdump"] = self.decoder.available()
                return self.status["satdump"]
            if action in {"sdr", "record"}:
                with self.receiver_factory(self.config.sdr) as receiver:
                    self.status["sdr"] = str(receiver.info())
                    if action == "record":
                        check_space(self.config.work_dir, receiver.actual_rate, 3, self.config.storage)
                        path = self.config.work_dir / f"test-{uuid.uuid4().hex}.cs16"
                        try:
                            result = receiver.record(path, 3, self.stop)
                            if not path.exists() or path.stat().st_size <= 0:
                                raise RuntimeError("SDR test recorded no data")
                            return f"SDR test received {result['samples']} samples. {self.status['sdr']}"
                        finally:
                            path.unlink(missing_ok=True)
                    return self.status["sdr"]
            raise ValueError("Unknown hardware action")
