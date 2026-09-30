import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin

import httpx


def sfu_to_si(sfu):
    if not math.isfinite(sfu) or sfu <= 0:
        raise ValueError("Solar flux must be positive and finite")
    return sfu * 1e-22


def y_from_db(sun_db, cold_db):
    if not math.isfinite(sun_db) or not math.isfinite(cold_db):
        raise ValueError("Power must be finite")
    return 10 ** ((sun_db - cold_db) / 10)


def sky_separation(first, second):
    az1, el1, az2, el2 = map(math.radians, (*first, *second))
    cosine = math.sin(el1) * math.sin(el2) + math.cos(el1) * math.cos(el2) * math.cos(az1 - az2)
    return math.degrees(math.acos(max(-1, min(1, cosine))))


def calculate_gt(sun_power, cold_power, frequency_hz, flux_sfu):
    if any(not math.isfinite(n) or n <= 0 for n in (sun_power, cold_power, frequency_hz)):
        raise ValueError("Positive finite power and frequency required")
    y = sun_power / cold_power
    if y <= 1:
        raise ValueError("Y must exceed 1; no credible Sun excess power measured")
    wavelength = 299792458 / frequency_hz
    gt = 8 * math.pi * 1.380649e-23 / (sfu_to_si(flux_sfu) * wavelength**2) * (y - 1)
    return dict(
        p_sun=sun_power,
        p_cold=cold_power,
        y=y,
        solar_flux_sfu=flux_sfu,
        solar_flux_si=sfu_to_si(flux_sfu),
        frequency_hz=frequency_hz,
        gt_linear=gt,
        gt_db_per_k=10 * math.log10(gt),
    )


@dataclass(frozen=True)
class SolarFlux:
    timestamp: datetime
    frequency_hz: float
    flux_sfu: float
    source_url: str = ""

    def metadata(self, measurement_frequency_hz):
        return {
            **asdict(self),
            "timestamp": self.timestamp.isoformat(),
            "frequency_difference_hz": self.frequency_hz - measurement_frequency_hz,
            "flux_column": "atmosphere-corrected, NOT normalized to 1 AU",
        }


def parse_wesis(text, source_url=""):
    """BKG SFX raw format (2023-05-10), one frequency per data row."""
    result = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 11:
            continue
        try:
            when = datetime.fromisoformat(fields[0].replace("Z", "+00:00"))
            frequency = float(fields[3])
            # fields[5] is normalized to 1 AU; fields[6] matches Sun distance now.
            flux = float(fields[6])
            if fields[9] != "00000000" or fields[10] != "00000000":
                continue
            if when.tzinfo is None or not math.isfinite(frequency) or frequency <= 0:
                continue
            sfu_to_si(flux)
            result.append(SolarFlux(when.astimezone(UTC), frequency, flux, source_url))
        except (ValueError, OverflowError):
            continue
    if not result:
        raise ValueError("WESIS file contains no valid unflagged solar flux measurements")
    return result


def select_flux(records, frequency, when, max_age_seconds):
    valid = [r for r in records if abs((r.timestamp - when).total_seconds()) <= max_age_seconds]
    if not valid:
        raise ValueError("No WESIS flux within the configured time tolerance; no G/T calculated")
    return min(
        valid,
        key=lambda r: (
            abs(r.frequency_hz - frequency),
            abs((r.timestamp - when).total_seconds()),
            r.timestamp,
        ),
    )


class WesisClient:
    def __init__(self, config, cache, fetch=None):
        self.config, self.cache = config, cache
        self.fetch = fetch or self._fetch
        cache.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _fetch(url):
        response = httpx.get(url, timeout=20, follow_redirects=True)
        response.raise_for_status()
        return response.text

    def get_flux(self, frequency, when):
        import re
        import time

        index = self.cache / "index.txt"
        try:
            if not index.exists() or time.time() - index.stat().st_mtime > 900:
                data = self.fetch(self.config.index_url)
                if not re.search(r"WETZ_SFX1_\d{8}_\d{4}_\w+\.SFX", data):
                    raise ValueError("Invalid WESIS machine-readable index")
                temp = index.with_suffix(".tmp")
                temp.write_text(data, encoding="utf-8")
                temp.replace(index)
        except (httpx.HTTPError, OSError, ValueError):
            if not index.exists():
                raise RuntimeError("Cannot obtain WESIS index; no G/T calculated") from None
        candidates = []
        for line in index.read_text(encoding="utf-8").splitlines():
            match = re.fullmatch(
                r"data_repository/sfx/\d{4}/\d{3}/WETZ_SFX1_(\d{8}_\d{4})_\w+\.SFX", line.strip()
            )
            if match:
                timestamp = datetime.strptime(match[1], "%Y%m%d_%H%M").replace(tzinfo=UTC)
                delta = abs((when - timestamp).total_seconds())
                if delta <= self.config.max_flux_age_seconds + 600:
                    candidates.append((delta, line.strip()))
        records = []
        for _, relative in sorted(candidates)[:6]:
            url = urljoin(self.config.index_url, relative)
            path = self.cache / relative.rsplit("/", 1)[1]
            try:
                if path.exists():
                    parsed = parse_wesis(path.read_text(encoding="utf-8"), url)
                else:
                    data = self.fetch(url)
                    parsed = parse_wesis(data, url)
                    temp = path.with_suffix(".tmp")
                    temp.write_text(data, encoding="utf-8")
                    temp.replace(path)
                records.extend(parsed)
            except (httpx.HTTPError, ValueError, OSError):
                continue
        if not records:
            raise RuntimeError(
                "No valid recent WESIS data; retry after publication delay or check cache/network"
            )
        return select_flux(records, frequency, when, self.config.max_flux_age_seconds)
