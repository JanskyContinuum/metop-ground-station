import math

import numpy as np


class HorizonMask:
    """Periodic linear interpolation; a visibility policy, not a collision model."""

    def __init__(self, points):
        if not points or any(
            not math.isfinite(a) or not math.isfinite(e) or not 0 <= a < 360 or not 0 <= e <= 90
            for a, e in points
        ):
            raise ValueError("Horizon points require azimuth [0,360) and elevation [0,90]")
        self.points = sorted(points)
        if len({a for a, _ in points}) != len(points):
            raise ValueError("Duplicate horizon azimuth")

    def elevation(self, azimuth):
        return float(np.interp(azimuth % 360, *zip(*self.points), period=360))

    def visible(self, azimuth, elevation):
        return elevation >= self.elevation(azimuth)
