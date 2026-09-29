import threading
from contextlib import contextmanager

from filelock import FileLock, Timeout


class HardwareBusy(RuntimeError):
    pass


class HardwareLock:
    """One lock shared by the web process and separate diagnostic/G/T commands."""

    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True)
        self.file = FileLock(root / "hardware.lock", timeout=0)
        self.thread = threading.Lock()
        self.owner = None

    @contextmanager
    def hold(self, owner):
        if not self.thread.acquire(blocking=False):
            raise HardwareBusy(f"Hardware busy: {self.owner}")
        acquired = False
        try:
            try:
                self.file.acquire()
                acquired = True
            except Timeout as exc:
                raise HardwareBusy("Hardware in use by another application or CLI utility") from exc
            self.owner = owner
            yield
        finally:
            self.owner = None
            if acquired:
                self.file.release()
            self.thread.release()
