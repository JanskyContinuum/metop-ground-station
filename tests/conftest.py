from datetime import timedelta
from pathlib import Path

import pytest

from groundstation.config import Config
from groundstation.orbit.passes import Pass, utcnow


@pytest.fixture
def config(tmp_path):
    return Config(
        mock=True,
        storage={"root": tmp_path / "data", "safety_margin_bytes": 0},
        rotor={"update_interval_sec": 0.1},
        passes={"preposition_seconds": 0},
    )


@pytest.fixture
def tle_text():
    return (Path(__file__).parent / "fixtures" / "metop.tle").read_text()


@pytest.fixture
def quick_pass():
    start = utcnow() + timedelta(seconds=0.1)
    end = start + timedelta(seconds=0.25)
    return Pass("METOP-C", start, end, start + (end - start) / 2, 65, ((start, end),), mock=True)
