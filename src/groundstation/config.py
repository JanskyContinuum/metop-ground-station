import os
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Station(Model):
    latitude_deg: float = Field(default=52.218835, ge=-90, le=90)
    longitude_deg: float = Field(default=21.010946, ge=-180, le=180)
    altitude_m: float = 120
    timezone: str = "Europe/Warsaw"


class Rotor(Model):
    host: str = ""
    port: int = Field(default=4533, ge=1, le=65535)
    azimuth_min_deg: float = -180
    azimuth_max_deg: float = 300
    elevation_min_deg: float = Field(default=50, ge=0, le=180)
    elevation_max_deg: float = Field(default=180, ge=0, le=180)
    clearance_azimuth_min_deg: float = Field(default=194, ge=0, lt=360)
    clearance_azimuth_max_deg: float = Field(default=210, gt=0, le=360)
    clearance_elevation_min_deg: float = Field(default=10, ge=0, le=180)
    park_azimuth_deg: float = 0
    park_elevation_deg: float = 50
    update_interval_sec: float = Field(default=1.5, ge=0.1, le=10)
    timeout_sec: float = Field(default=2, gt=0, le=10)
    limits_confirmed: bool = False
    settle_timeout_sec: float = Field(default=120, gt=0, le=600)
    position_tolerance_deg: float = Field(default=1, gt=0, le=5)

    @model_validator(mode="after")
    def limits(self):
        if not self.azimuth_min_deg <= self.park_azimuth_deg <= self.azimuth_max_deg:
            raise ValueError("Park azimuth must lie inside mechanical limits")
        if not self.elevation_min_deg <= self.park_elevation_deg <= self.elevation_max_deg:
            raise ValueError("Park elevation must lie inside mechanical limits")
        if self.azimuth_min_deg >= self.azimuth_max_deg:
            raise ValueError("Invalid azimuth limits")
        if self.clearance_azimuth_min_deg >= self.clearance_azimuth_max_deg:
            raise ValueError("Invalid clearance sector")
        if (
            self.clearance_azimuth_min_deg
            < self.park_azimuth_deg % 360
            < self.clearance_azimuth_max_deg
        ):
            if self.park_elevation_deg < self.clearance_elevation_min_deg:
                raise ValueError("Park elevation violates sector clearance")
        return self


class SDR(Model):
    driver: str = "sdrplay"
    center_frequency_hz: float = Field(default=1701300000, gt=0)
    sample_rate_hz: float = Field(default=5000000, gt=0)
    gain: float = 40
    agc: bool = False
    biastee: bool = False
    stall_timeout_sec: float = Field(default=5, gt=1, le=30)


class SatDump(Model):
    executable: str = "satdump"
    command_prefix: list[str] = Field(default_factory=lambda: ["pipeline"])
    pipeline: str = "metop_ahrpt"
    baseband_format: str = "cs16"
    image_glob: str | None = None
    timeout_sec: float = Field(default=1800, gt=0)


class TrackingLimits(Model):
    start_azimuth_gt_deg: float = Field(default=200, ge=0, lt=360)
    start_elevation_gt_deg: float = Field(default=50, ge=0, lt=90)
    stop_elevation_deg: float = Field(default=20, ge=0, le=90)

    @model_validator(mode="after")
    def thresholds(self):
        if self.stop_elevation_deg >= self.start_elevation_gt_deg:
            raise ValueError("Tracking stop elevation must be below start elevation")
        return self

    def can_start(self, azimuth, elevation):
        return azimuth % 360 > self.start_azimuth_gt_deg and elevation > self.start_elevation_gt_deg

    def can_continue(self, elevation):
        return elevation > self.stop_elevation_deg


class Passes(Model):
    prediction_hours: float = Field(default=2, gt=0, le=24)
    minimum_max_elevation_deg: float = Field(default=50, ge=0, le=90)
    preposition_seconds: float = Field(default=90, ge=0, le=600)
    satellites: list[str] = Field(default_factory=lambda: ["METOP-B", "METOP-C"])
    sample_seconds: float = Field(default=2, ge=0.5, le=10)


class TLE(Model):
    max_age_hours: float = Field(default=24, gt=0)
    url: str = "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=TLE"
    retry_seconds: float = Field(default=900, ge=60)


class Storage(Model):
    root: Path = Path("data")
    work: Path = Path("work")
    gallery: Path = Path("gallery")
    failed_raw_retention_hours: float = Field(default=24, gt=0)
    safety_margin_bytes: int = Field(default=2_000_000_000, ge=0)
    size_margin_factor: float = Field(default=1.2, ge=1)


class Web(Model):
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)


class GT(Model):
    index_url: str = "https://wesis.bkg.bund.de/wesis_sfx_files_latest.txt"
    max_flux_age_seconds: float = Field(default=3600, gt=0)
    safe_elevation_deg: float = Field(default=20, ge=0, le=90)
    cold_offset_deg: float = Field(default=30, ge=10, le=180)
    settle_seconds: float = Field(default=3, ge=0)


class Config(Model):
    station: Station = Field(default_factory=Station)
    rotor: Rotor = Field(default_factory=Rotor)
    horizon_mask: list[tuple[float, float]] = Field(
        default_factory=lambda: [(0, 50), (79.9, 50), (80, 30), (270, 30), (270.1, 50)]
    )
    sdr: SDR = Field(default_factory=SDR)
    satdump: SatDump = Field(default_factory=SatDump)
    passes: Passes = Field(default_factory=Passes)
    tracking_limits: TrackingLimits = Field(default_factory=TrackingLimits)
    tle: TLE = Field(default_factory=TLE)
    storage: Storage = Field(default_factory=Storage)
    web: Web = Field(default_factory=Web)
    gt: GT = Field(default_factory=GT)
    mock: bool = False

    @model_validator(mode="after")
    def validate_settings(self):
        ZoneInfo(self.station.timezone)
        if self.sdr.driver != "sdrplay" or self.satdump.baseband_format != "cs16":
            raise ValueError("Only SDRplay CS16 acquisition is supported")
        from groundstation.orbit.horizon import HorizonMask

        HorizonMask(self.horizon_mask)
        root = self.storage.root.resolve()
        paths = [(root / p).resolve() for p in (self.storage.work, self.storage.gallery)]
        for path in paths:
            if path == root or not path.is_relative_to(root):
                raise ValueError("work/gallery must be distinct subdirectories inside storage.root")
        if paths[0].is_relative_to(paths[1]) or paths[1].is_relative_to(paths[0]):
            raise ValueError("work and gallery may not overlap")
        return self

    @property
    def work_dir(self):
        return (self.storage.root / self.storage.work).resolve()

    @property
    def gallery_dir(self):
        return (self.storage.root / self.storage.gallery).resolve()


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path or os.getenv("GROUNDSTATION_CONFIG", "config/station.yaml"))
    mock = os.getenv("GROUNDSTATION_MOCK") == "1"
    if not path.exists() and not mock:
        raise ValueError(f"Copy config/station.example.yaml to {path} and confirm station settings")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    data = data or {}
    if mock:
        data["mock"] = True
    config = Config.model_validate(data)
    # Demo receptions never mix with real station results.
    if config.mock:
        config.storage.root = config.storage.root / "mock"
    return config
