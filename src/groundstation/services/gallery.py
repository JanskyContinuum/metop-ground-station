import json
import logging
import os
import re
import shutil
import uuid
from datetime import datetime

from PIL import Image

log = logging.getLogger(__name__)


def store_result(root, source, metadata):
    when = datetime.fromisoformat(metadata["aos"])
    satellite = re.sub(r"[^A-Za-z0-9_-]", "_", metadata["satellite"])
    parent = root / when.strftime("%Y")
    parent.mkdir(parents=True, exist_ok=True)
    name = f"{when:%Y-%m-%d_%H%M%S}_{satellite}"
    destination = parent / name
    if destination.exists():
        raise FileExistsError("Gallery reception already exists; refusing to overwrite")
    staging = parent / f".pending-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        with Image.open(source) as image:
            image.convert("RGB").save(staging / "avhrr.png", format="PNG")
        with Image.open(staging / "avhrr.png") as image:
            image.verify()
        with (staging / "metadata.json").open("w", encoding="utf-8") as stream:
            json.dump(metadata, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        with (staging / "avhrr.png").open("rb+") as stream:
            os.fsync(stream.fileno())
        staging.rename(destination)
        # Sync the directory entry on the Linux station before raw removal.
        if os.name != "nt":
            descriptor = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return destination
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def scan_gallery(root):
    results = []
    for path in root.glob("[0-9][0-9][0-9][0-9]/*/metadata.json"):
        if path.parent.name.startswith("."):
            continue
        image = path.parent / "avhrr.png"
        if not path.resolve().is_relative_to(root.resolve()) or not image.resolve().is_relative_to(
            root.resolve()
        ):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("satellite"), str):
                continue
            when = datetime.fromisoformat(data["aos"])
            if when.tzinfo is None or not image.is_file():
                continue
            results.append({**data, "image_url": "/images/" + image.relative_to(root).as_posix()})
        except (OSError, ValueError, KeyError, TypeError):
            log.warning("Skipping incomplete gallery entry %s", path.parent.name)
    return sorted(results, key=lambda item: item["aos"], reverse=True)
