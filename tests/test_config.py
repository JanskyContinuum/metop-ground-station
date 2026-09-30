import pytest

from groundstation.config import Config, load_config


def test_example_loads_and_live_requires_local_config(monkeypatch, tmp_path):
    monkeypatch.delenv("GROUNDSTATION_MOCK", raising=False)
    assert load_config("config/station.example.yaml").rotor.host == ""
    with pytest.raises(ValueError):
        load_config(tmp_path / "missing.yaml")


def test_mock_is_offline_and_uses_separate_root(monkeypatch, tmp_path):
    monkeypatch.setenv("GROUNDSTATION_MOCK", "1")
    config = load_config(tmp_path / "missing.yaml")
    assert config.mock and config.storage.root.name == "mock"


@pytest.mark.parametrize(
    "settings",
    [
        {"storage": {"work": "../outside"}},
        {"storage": {"gallery": "work/gallery"}},
        {"rotor": {"park_elevation_deg": 0}},
        {"station": {"latitude_deg": float("nan")}},
        {"sdr": {"driver": "hydrasdr"}},
        {"sdr": {"sample_rate_hz": 0}},
    ],
)
def test_invalid_configuration(settings):
    with pytest.raises(ValueError):
        Config(**settings)
