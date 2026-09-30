import json
import logging
import math
import shutil
from datetime import UTC, datetime, timedelta

log = logging.getLogger(__name__)


def expected_bytes(rate, seconds):
    if not math.isfinite(rate) or not math.isfinite(seconds) or rate <= 0 or seconds < 0:
        raise ValueError("Invalid recording rate or duration")
    return math.ceil(rate * seconds * 4)


def check_space(path, rate, seconds, storage):
    path.mkdir(parents=True, exist_ok=True)
    required = math.ceil(expected_bytes(rate, seconds) * storage.size_margin_factor)
    required += storage.safety_margin_bytes
    free = shutil.disk_usage(path).free
    if free < required:
        raise RuntimeError(
            f"Insufficient disk: need {required / 1e9:.2f} GB, have {free / 1e9:.2f} GB"
        )
    return required


def remove_work(directory, root):
    """Delete only a direct observation directory within the configured work root."""
    root = root.resolve()
    resolved = directory.resolve()
    if directory.is_symlink() or resolved.parent != root or not directory.name.startswith("obs-"):
        raise ValueError("Refusing cleanup outside owned observation directory")
    shutil.rmtree(resolved)


def mark_failed(directory, message):
    temp = directory / "failed.tmp"
    temp.write_text(
        json.dumps({"failed_at": datetime.now(UTC).isoformat(), "error": message}), encoding="utf-8"
    )
    temp.replace(directory / "failed.json")


def cleanup_failed(root, retention_hours, now=None):
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=retention_hours)
    removed = []
    for marker in root.glob("obs-*/failed.json"):
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            when = datetime.fromisoformat(data["failed_at"])
            if when.tzinfo is None:
                continue
            if when < cutoff:
                remove_work(marker.parent, root)
                removed.append(marker.parent.name)
        except (OSError, ValueError, KeyError, TypeError):
            log.exception("Could not clean failed observation %s", marker.parent.name)
    return removed


def recover_interrupted(root):
    """Called only after acquiring the application singleton lock on startup."""
    for directory in root.glob("obs-*"):
        if (directory / "observation.json").is_file() and not (directory / "failed.json").exists():
            mark_failed(directory, "Interrupted previous application run; retained for inspection")
