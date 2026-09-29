from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from math import ceil

from pyorbital.orbital import Orbital

from groundstation.orbit.horizon import HorizonMask


def utcnow():
    return datetime.now(UTC)


def orbital_time(when):
    """PyOrbital's numpy datetime boundary expects naive UTC; nowhere else does."""
    if when.tzinfo is None:
        raise ValueError("Timezone-aware time required")
    return when.astimezone(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class Pass:
    satellite: str
    aos: datetime
    los: datetime
    tca: datetime
    max_elevation: float
    windows: tuple[tuple[datetime, datetime], ...]
    orbital: object = field(default=None, repr=False, compare=False)
    tle_epoch: str | None = None
    mock: bool = False

    @property
    def id(self):
        return sha256(f"{self.satellite}:{self.aos.isoformat()}".encode()).hexdigest()[:20]

    @property
    def duration(self):
        return (self.los - self.aos).total_seconds()

    @property
    def usable_duration(self):
        return sum((end - start).total_seconds() for start, end in self.windows)

    @property
    def recording_window(self):
        return max(self.windows, key=lambda w: w[1] - w[0])

    def position(self, when, station):
        if self.mock:
            fraction = (when - self.aos).total_seconds() / self.duration
            return 120 + 20 * fraction, 65.0
        az, el = self.orbital.get_observer_look(
            orbital_time(when), station.longitude_deg, station.latitude_deg, station.altitude_m / 1000
        )
        return float(az), float(el)


def visibility_windows(aos, los, position, mask, rotor, step):
    windows, start = [], None
    count = ceil((los - aos).total_seconds() / step)
    for i in range(count + 1):
        when = min(aos + timedelta(seconds=i * step), los)
        az, el = position(when)
        visible = mask.visible(az, el) and rotor.elevation_min_deg <= el <= rotor.elevation_max_deg
        # Test equivalent azimuths without opening a rotor connection.
        from groundstation.hardware.rotor import legal_azimuth
        try:
            legal_azimuth(az, 0, rotor)
        except ValueError:
            visible = False
        if visible and start is None and when < los:
            start = when
        if start is not None and (not visible or when == los):
            # End at the last known valid sample, never across a mask gap.
            end = when if visible else max(start, when - timedelta(seconds=step))
            if end > start:
                windows.append((start, end))
            start = None
    return tuple(windows)


def predict(config, records, now=None):
    now = now or utcnow()
    result = []
    end = now + timedelta(hours=config.passes.prediction_hours)
    mask = HorizonMask(config.horizon_mask)
    for name in config.passes.satellites:
        record = records.get(name.upper())
        if not record:
            continue
        orbital = Orbital(name, line1=record.line1, line2=record.line2)
        station = config.station
        # Include an ongoing pass, but never select a visibility window already over.
        search_start = now - timedelta(minutes=20)
        raw = orbital.get_next_passes(
            orbital_time(search_start), ceil(config.passes.prediction_hours + 1),
            station.longitude_deg, station.latitude_deg, station.altitude_m / 1000,
        )
        for aos, los, tca in raw:
            aos, los, tca = (t.replace(tzinfo=UTC) for t in (aos, los, tca))
            if los <= now or aos > end:
                continue
            draft = Pass(name, aos, los, tca, 0, (), orbital, record.epoch.isoformat())
            peak = draft.position(tca, station)[1]
            if peak < config.passes.minimum_max_elevation_deg:
                continue
            windows = visibility_windows(
                aos, los, lambda t: draft.position(t, station), mask,
                config.rotor, config.passes.sample_seconds,
            )
            windows = tuple(w for w in windows if w[1] > now)
            if windows:
                result.append(Pass(name, aos, los, tca, peak, windows, orbital, draft.tle_epoch))
    return sorted(result, key=lambda p: p.aos)


def mock_passes(now=None):
    now = now or utcnow()
    result = []
    for seconds in (30, 180, 360):
        start = now + timedelta(seconds=seconds)
        end = start + timedelta(seconds=8)
        result.append(Pass("METOP-C", start, end, start + (end - start) / 2,
                           65, ((start, end),), mock=True))
    return result
