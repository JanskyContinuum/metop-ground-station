import pytest

from groundstation.orbit.horizon import HorizonMask


def test_periodic_mask():
    mask = HorizonMask([(10, 20), (180, 40), (350, 60)])
    assert mask.elevation(0) == pytest.approx(40)
    assert mask.elevation(360) == mask.elevation(0)
    assert mask.elevation(-10) == 60
    assert not mask.visible(180, 39)
    assert mask.visible(180, 40)


@pytest.mark.parametrize("points", [[], [(0, 10), (0, 20)], [(360, 20)], [(0, float("nan"))]])
def test_invalid_mask(points):
    with pytest.raises(ValueError):
        HorizonMask(points)
