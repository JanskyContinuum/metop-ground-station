import shutil
import subprocess
import time

from PIL import Image, UnidentifiedImageError


def find_avhrr(output, override=None):
    root = output.resolve()
    candidates = []
    if override and (override.startswith(("/", "\\")) or ".." in override.split("/")):
        raise ValueError("AVHRR glob must stay inside SatDump output")
    for path in output.glob(override or "**/*"):
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
            continue
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            continue
        name = path.relative_to(output).as_posix().lower()
        if not override and "avhrr" not in name:
            continue
        if any(part in path.stem.lower() for part in ("thumb", "preview", "map_overlay", "mask")):
            continue
        try:
            with Image.open(path) as image:
                if min(image.size) < 64:
                    continue
                area = image.width * image.height
                image.verify()
            priority = 0 if any(word in name for word in ("composite", "rgb", "color")) else 1
            candidates.append((priority, -area, name, path))
        except (OSError, ValueError, UnidentifiedImageError):
            continue
    if not candidates:
        raise RuntimeError("SatDump produced no readable useful AVHRR image; raw retained")
    return min(candidates)[-1]


class SatDump:
    def __init__(self, config):
        self.config = config

    def command(self, raw, output, rate):
        return [self.config.executable, *self.config.command_prefix, self.config.pipeline,
                "baseband", str(raw), str(output), f"--samplerate={rate:g}",
                f"--baseband_format={self.config.baseband_format}"]

    def available(self):
        found = shutil.which(self.config.executable)
        if not found:
            raise RuntimeError("SatDump executable not found; install/verify it manually")
        return found

    def process(self, raw, output, rate, stop):
        self.available()
        output.mkdir(parents=True, exist_ok=True)
        # File-backed log prevents unbounded RAM capture and pipe deadlocks.
        with (output.parent / "satdump.log").open("wb") as log:
            process = subprocess.Popen(self.command(raw, output, rate), stdout=log,
                                       stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + self.config.timeout_sec
                while process.poll() is None:
                    if stop.wait(0.2):
                        raise InterruptedError("SatDump cancelled; raw retained")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("SatDump timed out; raw retained")
                if process.returncode != 0:
                    raise RuntimeError(f"SatDump exited {process.returncode}; see retained satdump.log")
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
