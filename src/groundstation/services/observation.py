import json
import logging
import threading
import uuid

from groundstation.orbit.horizon import HorizonMask
from groundstation.orbit.passes import utcnow
from groundstation.services.cleanup import check_space, mark_failed, remove_work
from groundstation.services.gallery import store_result
from groundstation.services.satdump import find_avhrr

log = logging.getLogger(__name__)


class Observation:
    def __init__(self, config, rotor, receiver_factory, decoder, hardware_lock):
        self.config, self.rotor = config, rotor
        self.receiver_factory, self.decoder, self.hardware_lock = (
            receiver_factory,
            decoder,
            hardware_lock,
        )
        self.motion_guard = threading.Lock()

    def emergency_stop(self, stop):
        # Set cancellation before serializing with motion, preventing a late P after STOP.
        stop.set()
        with self.motion_guard:
            self.rotor.stop()

    def _point(self, az, el, stop):
        with self.motion_guard:
            if stop.is_set():
                raise InterruptedError("Observation stopped")
            return self.rotor.set_position(az, el)

    def execute(self, selected, stop, state):
        config = self.config
        with self.hardware_lock.hold(f"pass {selected.satellite}"):
            directory = config.work_dir / f"obs-{uuid.uuid4().hex}"
            directory.mkdir(parents=True)
            (directory / "observation.json").write_text(
                json.dumps({"pass": selected.id, "started": utcnow().isoformat()}), encoding="utf-8"
            )
            raw = directory / "capture.cs16"
            tracker = None
            tracking_stop = threading.Event()
            errors = []
            try:
                start, end = selected.recording_window
                state("PREPARING")
                check_space(
                    directory,
                    config.sdr.sample_rate_hz,
                    max(0, (end - utcnow()).total_seconds()),
                    config.storage,
                )
                target = self._point(*selected.position(max(start, utcnow()), config.station), stop)
                self.rotor.wait_for_position(target, stop)
                if stop.wait(max(0, (start - utcnow()).total_seconds())):
                    raise InterruptedError("Observation cancelled before recording")
                if utcnow() >= end:
                    raise RuntimeError("Usable visibility ended before preparation completed")
                state("TRACKING")
                mask = HorizonMask(config.horizon_mask)

                def track():
                    try:
                        while not tracking_stop.is_set() and not stop.is_set() and utcnow() < end:
                            az, el = selected.position(utcnow(), config.station)
                            if not mask.visible(az, el):
                                # Do not concatenate recordings across an obstruction gap.
                                tracking_stop.set()
                                break
                            self._point(az, el, stop)
                            tracking_stop.wait(config.rotor.update_interval_sec)
                    except Exception as exc:
                        errors.append(exc)
                        tracking_stop.set()

                # The SDR loop and tracking run independently, so network latency cannot stall IQ reads.
                class StopRecording:
                    def is_set(self):
                        return stop.is_set() or tracking_stop.is_set()

                    def wait(self, seconds):
                        import time

                        deadline = time.monotonic() + seconds
                        while not self.is_set() and time.monotonic() < deadline:
                            stop.wait(min(0.1, max(0, deadline - time.monotonic())))
                        return self.is_set()

                with self.receiver_factory(config.sdr) as receiver:
                    duration = (end - utcnow()).total_seconds()
                    if duration <= 0:
                        raise RuntimeError("Usable visibility ended while opening SDR")
                    check_space(directory, receiver.actual_rate, duration, config.storage)
                    tracker = threading.Thread(target=track, name="rotor-tracking")
                    tracker.start()
                    recording = receiver.record(raw, duration, StopRecording())
                tracking_stop.set()
                tracker.join()
                if errors:
                    raise errors[0]
                if stop.is_set():
                    raise InterruptedError("Observation stopped; raw retained")
                with self.motion_guard:
                    if stop.is_set():
                        raise InterruptedError("Observation stopped")
                    target = self.rotor.park()
                self.rotor.wait_for_position(target, stop)
                state("PROCESSING")
                products = directory / "products"
                self.decoder.process(raw, products, recording["actual_sample_rate_hz"], stop)
                source = find_avhrr(products, config.satdump.image_glob)
                if stop.is_set():
                    raise InterruptedError("Processing cancelled; raw retained")
                metadata = dict(
                    satellite=selected.satellite,
                    aos=selected.aos.isoformat(),
                    los=selected.los.isoformat(),
                    tca=selected.tca.isoformat(),
                    max_elevation=selected.max_elevation,
                    **recording,
                    frequency_hz=config.sdr.center_frequency_hz,
                    requested_sample_rate_hz=config.sdr.sample_rate_hz,
                    gain=config.sdr.gain,
                    agc=config.sdr.agc,
                    biastee=config.sdr.biastee,
                    pipeline=config.satdump.pipeline,
                    tle_epoch=selected.tle_epoch,
                    source_image=source.relative_to(products).as_posix(),
                    simulated=config.mock,
                )
                destination = store_result(config.gallery_dir, source, metadata)
                remove_work(directory, config.work_dir)
                state("COMPLETE")
                return destination
            except Exception as exc:
                if directory.exists():
                    mark_failed(directory, str(exc))
                raise
            finally:
                tracking_stop.set()
                if tracker is not None:
                    tracker.join()
                # Cancellation/failure only stops; it never automatically resumes motion to park.
                try:
                    with self.motion_guard:
                        self.rotor.stop()
                except Exception:
                    log.exception("Rotor STOP failed; check the physical controller")
