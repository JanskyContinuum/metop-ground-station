import time
import sys
from pyorbital.orbital import Orbital
from SatelliteTracker import SatelliteTracker
from RotorController import RotorController

# --- KONFIGURACJA ---
STATION_LAT = 52.218835
STATION_LON = 21.010946
STATION_ALT = 120.0
ROTOR_PORT = '/dev/ttyUSB0'

# Dokładnie to, co wpisałeś w pierwszej linijce pliku txt!
TARGET_SATELLITE = "STARLINK-1664"
TLE_FILE = "starlink.txt"


# --------------------

# SZYBKI HACK: Nadpisujemy metodę w locie, żebyś nie musiał ręcznie
# edytować SatelliteTracker.py i usuwać "weather.txt"
def custom_get_orbital(self, satellite_name):
    sat_key = satellite_name.upper()
    if sat_key not in self._satellites:
        self._satellites[sat_key] = Orbital(sat_key, tle_file=TLE_FILE)
    return self._satellites[sat_key]


SatelliteTracker._get_orbital = custom_get_orbital


def main():
    print("=" * 50)
    print(f" ŚLEDZENIE STARLINKA (Plik: {TLE_FILE})")
    print("=" * 50)

    tracker = SatelliteTracker(STATION_LAT, STATION_LON, STATION_ALT)
    rotor = RotorController(serial_port=ROTOR_PORT)

    try:
        while True:
            az, el = tracker.get_position(TARGET_SATELLITE)
            if az is not None and el is not None:
                rotor.set_position(az, el)
            else:
                print(f"\n[ERROR] Nie mogę odczytać TLE. Czy plik ma 3 linijki i pierwsza to '{TARGET_SATELLITE}'?")
                sys.exit(1)

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n[!] Przerwano. Zatrzymuję stację.")
    finally:
        rotor.set_position(0.0, 20.0)  # Parkowanie na 20st elewacji


if __name__ == "__main__":
    main()
