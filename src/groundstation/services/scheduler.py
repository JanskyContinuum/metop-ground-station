import logging
import threading
from datetime import timedelta

from groundstation.orbit.passes import utcnow

log = logging.getLogger(__name__)


class Scheduler:
    """Volatile selections; one loop and at most one active observation."""

    def __init__(self, observation, preposition_seconds):
        self.observation = observation
        self.preposition_seconds = preposition_seconds
        self.selected = {}
        self.mutex = threading.RLock()
        self.shutdown_event = threading.Event()
        self.cancel_event = threading.Event()
        self.active = None
        self.state = "IDLE"
        self.error = None
        self.thread = None
        self.halted = False

    def interval(self, item):
        start, end = item.recording_window
        return start - timedelta(seconds=self.preposition_seconds), end

    def schedule(self, item):
        with self.mutex:
            if self.halted:
                raise ValueError("Station stopped; resume scheduling explicitly first")
            if item.recording_window[1] <= utcnow():
                raise ValueError("Pass usable interval has already ended")
            start, end = self.interval(item)
            for other in [*self.selected.values(), *([self.active] if self.active else [])]:
                left, right = self.interval(other)
                if start < right and left < end:
                    raise ValueError(
                        f"Pass conflicts with selected/running {other.satellite}, including preposition"
                    )
            self.selected[item.id] = item
            if not self.active:
                self.state = "WAITING"

    def cancel(self, identifier):
        with self.mutex:
            if self.active and self.active.id == identifier:
                self.cancel_event.set()
            elif identifier in self.selected:
                del self.selected[identifier]
            else:
                raise ValueError("Pass is no longer selected")
            if not self.active and not self.selected:
                self.state = "IDLE"

    def stop(self):
        self.halt()
        self.observation.emergency_stop(self.cancel_event)

    def halt(self):
        with self.mutex:
            self.halted = True
            self.selected.clear()
            self.cancel_event.set()
            self.error = "STOP requested; selections cleared. Resume scheduling explicitly."

    def resume(self):
        with self.mutex:
            if self.active:
                raise ValueError("Wait for active observation to stop before resuming")
            self.halted, self.error, self.state = False, None, "IDLE"

    def snapshot(self):
        with self.mutex:
            return dict(
                state=self.state,
                error=self.error,
                active=self.active,
                selected=sorted(self.selected.values(), key=lambda p: p.recording_window[0]),
                halted=self.halted,
            )

    def _state(self, value):
        with self.mutex:
            self.state = value

    def tick(self, now=None):
        now = now or utcnow()
        with self.mutex:
            if self.halted or self.active or self.shutdown_event.is_set():
                return
            for key, item in list(self.selected.items()):
                if item.recording_window[1] <= now:
                    del self.selected[key]
                    self.error = f"Missed {item.satellite}: station was busy or pass expired"
                    self.state = "FAILED"
            pending = sorted(self.selected.values(), key=lambda p: self.interval(p)[0])
            if not pending or self.interval(pending[0])[0] > now:
                return
            item = pending[0]
            self.active = self.selected.pop(item.id)
            self.cancel_event.clear()
            self.error = None
        try:
            self.observation.execute(item, self.cancel_event, self._state)
        except Exception as exc:
            log.exception("Observation failed")
            with self.mutex:
                self.error, self.state = str(exc), "FAILED"
        finally:
            with self.mutex:
                self.active = None

    def start(self):
        def run():
            while not self.shutdown_event.wait(0.2):
                self.tick()

        self.thread = threading.Thread(target=run, name="pass-scheduler")
        self.thread.start()

    def close(self):
        self.shutdown_event.set()
        self.cancel_event.set()
        if self.thread:
            self.thread.join()
        with self.mutex:
            self.selected.clear()
