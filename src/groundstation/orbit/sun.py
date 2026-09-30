def sun_position(station, when):
    from astropy import units as u
    from astropy.coordinates import AltAz, EarthLocation, get_sun
    from astropy.time import Time
    from astropy.utils import iers

    if when.tzinfo is None:
        raise ValueError("Sun calculation requires timezone-aware UTC")
    location = EarthLocation(
        lat=station.latitude_deg * u.deg,
        lon=station.longitude_deg * u.deg,
        height=station.altitude_m * u.m,
    )
    # Bundled IERS tables avoid an unexpected network dependency during pointing.
    with iers.conf.set_temp("auto_download", False):
        sun = get_sun(Time(when)).transform_to(AltAz(obstime=Time(when), location=location))
    return float(sun.az.deg), float(sun.alt.deg)
