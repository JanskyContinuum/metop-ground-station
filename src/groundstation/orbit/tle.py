import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from pyorbital.tlefile import Tle

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Elements:
    name: str
    line1: str
    line2: str
    epoch: datetime


def parse_tle(text: str) -> dict[str, Elements]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines or len(lines) % 3:
        raise ValueError("Expected named three-line TLE records")
    records = {}
    for i in range(0, len(lines), 3):
        name, first, second = lines[i : i + 3]
        name = name.removeprefix("0 ").strip().upper()
        for number, line in enumerate((first, second), 1):
            if len(line) != 69 or not line.startswith(f"{number} ") or not line[-1].isdigit():
                raise ValueError("Invalid TLE line structure")
            checksum = sum(int(c) if c.isdigit() else int(c == "-") for c in line[:68]) % 10
            if checksum != int(line[-1]):
                raise ValueError("Invalid TLE checksum")
        if first[2:7] != second[2:7] or name in records:
            raise ValueError("TLE catalog mismatch or duplicate name")
        year = int(first[18:20])
        year += 1900 if year >= 57 else 2000
        day = float(first[20:32])
        if not 1 <= day < 367:
            raise ValueError("Invalid TLE epoch")
        epoch = datetime(year, 1, 1, tzinfo=UTC) + timedelta(days=day - 1)
        # Validate orbital fields as well as checksums before cache replacement.
        Tle(name, line1=first, line2=second)
        records[name] = Elements(name, first, second, epoch)
    return records


class TLEManager:
    def __init__(self, config, root: Path, fetch=None):
        self.config = config
        self.path = root / "tle" / "weather.tle"
        self.fetch = fetch or self._fetch
        self.records = {}
        self.warning = None
        self.last_attempt = -float("inf")
        self.lock = threading.Lock()

    @staticmethod
    def _fetch(url):
        response = httpx.get(url, timeout=20, follow_redirects=True)
        response.raise_for_status()
        return response.text

    def age_hours(self):
        if not self.path.exists():
            return None
        return max(0, (time.time() - self.path.stat().st_mtime) / 3600)

    def load(self, force=False):
        with self.lock:
            old = self.records
            cache_valid = False
            if self.path.exists():
                try:
                    old = parse_tle(self.path.read_text(encoding="utf-8"))
                    cache_valid = True
                except (ValueError, OSError) as exc:
                    self.warning = f"Invalid TLE cache: {exc}"
            age = self.age_hours()
            if (
                old
                and cache_valid
                and age is not None
                and age < self.config.max_age_hours
                and not force
            ):
                self.records = old
                return old
            if time.monotonic() - self.last_attempt < self.config.retry_seconds:
                return old
            self.last_attempt = time.monotonic()
            try:
                text = self.fetch(self.config.url)
                new = parse_tle(text)
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temp = self.path.with_suffix(".tmp")
                with temp.open("w", encoding="utf-8") as stream:
                    stream.write(text)
                    stream.flush()
                    os.fsync(stream.fileno())
                temp.replace(self.path)
                self.records, self.warning = new, None
            except (httpx.HTTPError, OSError, ValueError) as exc:
                self.records = old
                self.warning = f"TLE refresh failed; {'using previous cache' if old else 'no passes available'}: {exc}"
                log.warning(self.warning)
            return self.records
