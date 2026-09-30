import sys
import threading

import pytest
from PIL import Image

from groundstation.services.satdump import SatDump, find_avhrr


def picture(path, size=(100, 100)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size).save(path)
    return path


def test_command_has_actual_rate_and_no_shell(config, tmp_path):
    command = SatDump(config.satdump).command(
        tmp_path / "raw with spaces.cs16", tmp_path / "out", 6000000
    )
    assert command[:4] == ["satdump", "pipeline", "metop_ahrpt", "baseband"]
    assert "--samplerate=6e+06" in command
    assert "--baseband_format=cs16" in command
    assert len(command) == 8


def test_selects_avhrr_composite_deterministically(tmp_path):
    picture(tmp_path / "MHS" / "large.png", (500, 500))
    picture(tmp_path / "AVHRR" / "channel_1.png", (400, 400))
    expected = picture(tmp_path / "AVHRR" / "composite.png")
    picture(tmp_path / "AVHRR" / "thumbnail.png")
    assert find_avhrr(tmp_path) == expected
    assert find_avhrr(tmp_path, "**/channel_1.png").name == "channel_1.png"


def test_missing_or_corrupt_image_fails(tmp_path):
    picture(tmp_path / "AMSU" / "image.png")
    (tmp_path / "avhrr.png").write_text("not an image")
    with pytest.raises(RuntimeError):
        find_avhrr(tmp_path)


def test_process_failure_and_timeout_are_reported(config, tmp_path):
    config.satdump.executable = sys.executable
    config.satdump.command_prefix = ["-c", "import sys; sys.exit(7)"]
    decoder = SatDump(config.satdump)
    with pytest.raises(RuntimeError, match="exited 7"):
        decoder.process(tmp_path / "raw", tmp_path / "out", 5000000, threading.Event())
    config.satdump.command_prefix = ["-c", "import time; time.sleep(30)"]
    config.satdump.timeout_sec = 0.1
    with pytest.raises(TimeoutError):
        decoder.process(tmp_path / "raw", tmp_path / "out", 5000000, threading.Event())
