import logging
import threading
import time

from filelock import FileLock

from groundstation.hardware.lock import HardwareLock
from groundstation.hardware.mocks import MockRotor, MockSatDump, MockSDR
from groundstation.hardware.rotor import RotorController
from groundstation.hardware.sdr import SDRReceiver
from groundstation.orbit.passes import mock_passes, predict, utcnow
from groundstation.orbit.tle import TLEManager
from groundstation.services.cleanup import cleanup_failed, recover_interrupted
from groundstation.services.diagnostics import Diagnostics
from groundstation.services.observation import Observation
from groundstation.services.satdump import SatDump
from groundstation.services.scheduler import Scheduler

log = logging.getLogger(__name__)


class Runtime:
    def __init__(self, config):
        self.config = config
        config.work_dir.mkdir(parents=True, exist_ok=True)
        config.gallery_dir.mkdir(parents=True, exist_ok=True)
        # ASGI startup and shutdown may execute in different thread-pool workers.
        self.instance_lock = FileLock(
            config.storage.root.resolve() / "application.lock", timeout=0, thread_local=False
        )
        self.lock = HardwareLock(config.storage.root.resolve())
        self.rotor = MockRotor(config.rotor) if config.mock else RotorController(config.rotor)
        self.receiver_factory = MockSDR if config.mock else SDRReceiver
        self.decoder = MockSatDump() if config.mock else SatDump(config.satdump)
        self.stop_event = threading.Event()
        self.diagnostics = Diagnostics(
            config, self.rotor, self.receiver_factory, self.decoder, self.lock, self.stop_event
        )
        self.tle = TLEManager(config.tle, config.storage.root)
        self.observation = Observation(
            config, self.rotor, self.receiver_factory, self.decoder, self.lock
        )
        self.scheduler = Scheduler(
            self.observation, 5 if config.mock else config.passes.preposition_seconds
        )
        self.passes = []
        self.prediction_error = None
        self.refresh_lock = threading.Lock()
        self.maintenance = None

    def refresh(self, force=False):
        with self.refresh_lock:
            if self.config.mock:
                # Preserve demo identities while available; make fresh ones when all have expired.
                if not any(p.los > utcnow() for p in self.passes):
                    self.passes = mock_passes()
                return
            try:
                records = self.tle.load(force=force)
                self.passes = predict(self.config, records)
                missing = [
                    name for name in self.config.passes.satellites if name.upper() not in records
                ]
                self.prediction_error = f"No TLE for {', '.join(missing)}" if missing else None
                old = [
                    name
                    for name in self.config.passes.satellites
                    if name.upper() in records
                    and (utcnow() - records[name.upper()].epoch).total_seconds()
                    > self.config.tle.max_age_hours * 3600
                ]
                if old:
                    self.prediction_error = (
                        f"Old orbital epochs for {', '.join(old)}; predictions may be inaccurate"
                    )
            except Exception as exc:
                self.prediction_error = str(exc)
                log.exception("Pass prediction failed")

    def start(self):
        self.instance_lock.acquire()
        try:
            recover_interrupted(self.config.work_dir)
            self.refresh()
            self.scheduler.start()

            def maintain():
                last = 0
                while not self.stop_event.wait(1):
                    if time.monotonic() - last >= 60:
                        self.refresh()
                        cleanup_failed(
                            self.config.work_dir, self.config.storage.failed_raw_retention_hours
                        )
                        last = time.monotonic()

            self.maintenance = threading.Thread(target=maintain, name="cache-maintenance")
            self.maintenance.start()
        except Exception:
            self.instance_lock.release()
            raise

    def close(self):
        self.stop_event.set()
        self.scheduler.close()
        if self.maintenance:
            self.maintenance.join()
        self.instance_lock.release()
