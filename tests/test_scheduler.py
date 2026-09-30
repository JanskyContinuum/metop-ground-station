from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock

import pytest

from groundstation.services.scheduler import Scheduler


def test_conflict_includes_preposition(quick_pass):
    scheduler = Scheduler(Mock(), 30)
    scheduler.schedule(quick_pass)
    second = replace(
        quick_pass,
        satellite="METOP-B",
        windows=((quick_pass.los + timedelta(seconds=10), quick_pass.los + timedelta(seconds=40)),),
    )
    with pytest.raises(ValueError, match="conflicts"):
        scheduler.schedule(second)
    scheduler.cancel(quick_pass.id)
    assert not scheduler.snapshot()["selected"]


def test_volatile_state_and_execution_once(quick_pass):
    observation = Mock()
    scheduler = Scheduler(observation, 30)
    scheduler.schedule(quick_pass)
    assert not Scheduler(observation, 30).snapshot()["selected"]
    scheduler.tick()
    scheduler.tick()
    observation.execute.assert_called_once()
    assert scheduler.active is None


def test_expired_pass_and_failure_report(quick_pass):
    observation = Mock()
    observation.execute.side_effect = RuntimeError("SDR unavailable")
    scheduler = Scheduler(observation, 30)
    scheduler.schedule(quick_pass)
    scheduler.tick()
    assert scheduler.state == "FAILED"
    assert scheduler.error == "SDR unavailable"


def test_stop_clears_queue_and_requires_resume(quick_pass):
    scheduler = Scheduler(Mock(), 30)
    scheduler.schedule(quick_pass)
    scheduler.stop()
    assert scheduler.halted and not scheduler.selected
    with pytest.raises(ValueError, match="stopped"):
        scheduler.schedule(quick_pass)
    scheduler.resume()
    scheduler.schedule(quick_pass)


def test_missed_pass_is_not_recorded(quick_pass):
    observation = Mock()
    scheduler = Scheduler(observation, 0)
    scheduler.schedule(quick_pass)
    scheduler.tick(quick_pass.los + timedelta(seconds=1))
    observation.execute.assert_not_called()
    assert "Missed" in scheduler.error
