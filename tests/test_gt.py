import math
from datetime import UTC, datetime, timedelta

import pytest

from groundstation.services.gt import (
    WesisClient,
    calculate_gt,
    parse_wesis,
    select_flux,
    sfu_to_si,
    y_from_db,
)


def row(freq=1665e6, flags="00000000 00000000"):
    return f"2026-09-29T12:00:00.000Z 180 40 {freq} 10000000 100 95 90 1 {flags}"


def test_y_factor_and_gt_equation():
    assert y_from_db(10, 0) == 10
    assert sfu_to_si(100) == pytest.approx(1e-20)
    result = calculate_gt(2, 1, 1701.3e6, 100)
    expected = 8 * math.pi * 1.380649e-23 / (1e-20 * (299792458 / 1701.3e6) ** 2)
    assert result["gt_linear"] == pytest.approx(expected)
    assert result["gt_db_per_k"] == pytest.approx(10 * math.log10(expected))


@pytest.mark.parametrize(
    "sun,cold,flux", [(1, 1, 100), (0, 1, 100), (2, 1, 0), (float("nan"), 1, 100)]
)
def test_invalid_measurement_rejected(sun, cold, flux):
    with pytest.raises(ValueError):
        calculate_gt(sun, cold, 1701.3e6, flux)


def test_wesis_uses_correct_flux_column_and_nearest_frequency():
    records = parse_wesis("\n".join([row(1e9), row(1415e6), row(1665e6), row(2695e6)]))
    when = datetime(2026, 9, 29, 12, tzinfo=UTC)
    selected = select_flux(records, 1701.3e6, when, 3600)
    assert selected.frequency_hz == 1665e6
    assert selected.flux_sfu == 95
    assert selected.metadata(1701.3e6)["frequency_difference_hz"] == -36.3e6


def test_wesis_rejects_flags_and_stale_data():
    for flags in ["00000001 00000000", "00000000 00000002"]:
        with pytest.raises(ValueError):
            parse_wesis(row(flags=flags))
    records = parse_wesis(row())
    with pytest.raises(ValueError):
        select_flux(records, 1701e6, records[0].timestamp + timedelta(hours=2), 3600)


def test_wesis_download_cache_and_offline(config, tmp_path):
    relative = "data_repository/sfx/2026/272/WETZ_SFX1_20260929_1200_02S.SFX"
    calls = []

    def fetch(url):
        calls.append(url)
        return relative if url.endswith(".txt") else row()

    client = WesisClient(config.gt, tmp_path, fetch)
    when = datetime(2026, 9, 29, 12, tzinfo=UTC)
    assert client.get_flux(1701.3e6, when).frequency_hz == 1665e6
    assert client.get_flux(1701.3e6, when).flux_sfu == 95
    assert len(calls) == 2


def test_public_bkg_fixture():
    from pathlib import Path

    rows = parse_wesis((Path(__file__).parent / "fixtures" / "wesis.sfx").read_text())
    selected = select_flux(rows, 1701.3e6, rows[0].timestamp, 3600)
    assert selected.frequency_hz == 1665e6
    assert selected.flux_sfu > 0


def test_sky_separation_at_high_elevation():
    from groundstation.services.gt import sky_separation

    assert sky_separation((0, 80), (30, 80)) < 10
    assert sky_separation((0, 50), (30, 50)) > 10
