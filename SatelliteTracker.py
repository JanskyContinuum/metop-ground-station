import logging
from datetime import datetime, timedelta
from pyorbital.orbital import Orbital


import urllib.request

# Ominięcie błędu 403 Forbidden z Celestrak
opener = urllib.request.build_opener()
opener.addheaders = [('User-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')]
urllib.request.install_opener(opener)

class SatelliteTracker:
    """
    Klasa do wyliczania przelotów i śledzenia satelitów na żywo.
    Wykorzystuje pyorbital, który automatycznie zarządza aktualizacjami TLE z Celestrak.
    """

    def __init__(self, lat, lon, alt=0.0):
        """
        Inicjalizacja stacji naziemnej.
        :param lat: Szerokość geograficzna (np. 52.2297 dla Warszawy)
        :param lon: Długość geograficzna (np. 21.0122 dla Warszawy)
        :param alt: Wysokość n.p.m. w metrach
        """
        self.lat = lat
        self.lon = lon
        self.alt = alt / 1000.0  # pyorbital oczekuje wysokości w kilometrach!

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("SatelliteTracker")

        # Słownik do przechowywania zainicjowanych obiektów Orbital,
        self._satellites = {}

        self.logger.info(f"Zainicjowano stację naziemną: Lat={self.lat}, Lon={self.lon}, Alt={self.alt}km")

    '''
    TO JEST WERSJA Z POBIERANIEM AUTOMATYCZNYM, czasami to sie wywala bo celestrak
    ma zabezpieczenia przed botami, druga wersja tej metody na dole umozliwa korzystanie
    z lokalnego pliku tle
    
    def _get_orbital(self, satellite_name):
        """
        Pobiera obiekt Orbital dla danego satelity.
        Jeśli go nie ma, tworzy go (co automatycznie pobiera/aktualizuje TLE).
        """
        sat_key = satellite_name.upper()
        if sat_key not in self._satellites:
            self.logger.info(f"Pobieranie/ładowanie TLE dla: {sat_key}...")
            try:
                # pyorbital sam ściągnie TLE z celestrak, jeśli plik jest starszy niż 24h
                self._satellites[sat_key] = Orbital(sat_key)
            except NotImplementedError as e:
                self.logger.error(f"Nie znaleziono satelity {sat_key} w bazie TLE! Błąd: {e}")
                return None
        return self._satellites[sat_key]
    '''


    # https://celestrak.org/NORAD/elements/weather.txt

    def _get_orbital(self, satellite_name):
        sat_key = satellite_name.upper()
        if sat_key not in self._satellites:
            self.logger.info(f"Ładowanie TLE z pliku lokalnego dla: {sat_key}...")
            try:
                #  argument tle_file wskazujący na pobrany plik
                self._satellites[sat_key] = Orbital(sat_key, tle_file='weather.txt')
            except Exception as e:
                self.logger.error(f"Nie udało się załadować satelity {sat_key} z pliku! Błąd: {e}")
                return None
        return self._satellites[sat_key]

    def get_good_passes(self, satellite_name, hours=24, min_elevation=50.0):
        """
        Szuka przelotów w ciągu najbliższych 'hours' godzin, których
        maksymalna elewacja przekracza 'min_elevation'.
        """
        orb = self._get_orbital(satellite_name)
        if not orb:
            return []

        now = datetime.utcnow()
        look_back_time = now - timedelta(minutes=10)

        self.logger.info(f"Szukam przelotów '{satellite_name}' na {hours}h do przodu (Min El: {min_elevation}°)...")

        # Pobieramy surowe czasy przelotów (horyzont ustawiony na 0 stopni)
        # Zwraca listę krotek: (AOS_time, LOS_time, TCA_time)
        raw_passes = orb.get_next_passes(look_back_time, hours, self.lon, self.lat, self.alt, horizon=0)

        good_passes = []

        for rise_time, fall_time, peak_time in raw_passes:
            # Obliczamy pozycję w momencie szczytu (peak_time), by sprawdzić max elewację
            az_peak, el_peak = orb.get_observer_look(peak_time, self.lon, self.lat, self.alt)

            if fall_time < now:
                continue

            if el_peak >= min_elevation:
                good_passes.append({
                    'satellite': satellite_name.upper(),
                    'aos': rise_time,  # Acquisition of Signal (Start)
                    'los': fall_time,  # Loss of Signal (Koniec)
                    'tca': peak_time,  # Time of Closest Approach (Szczyt)
                    'max_elev': round(el_peak, 1),
                    'duration_sec': (fall_time - rise_time).total_seconds()
                })

        self.logger.info(f"Znaleziono {len(good_passes)} przelotów spełniających kryteria.")
        return good_passes

    def get_position(self, satellite_name, target_time=None):
        """
        Zwraca aktualny Azymut i Elewację satelity dla podanego czasu
        (lub dla obecnego momentu, jeśli time nie jest podany).
        """
        orb = self._get_orbital(satellite_name)
        if not orb:
            return None, None

        if target_time is None:
            target_time = datetime.utcnow()

        # get_observer_look zwraca (Azymut, Elewacja) w stopniach
        az, el = orb.get_observer_look(target_time, self.lon, self.lat, self.alt)
        return round(az, 2), round(el, 2)



if __name__ == "__main__":
    # Współrzędne Warszawa
    STATION_LAT = 52.218835
    STATION_LON = 21.010946
    STATION_ALT = 120.0  # metry

    tracker = SatelliteTracker(STATION_LAT, STATION_LON, STATION_ALT)


    # przeloty MetOp-B na najbliższe 24h

    passes = tracker.get_good_passes("METOP-B", hours=24, min_elevation=50.0)

    for p in passes:
        print("\n--- ZNALEZIONY PRZELOT ---")
        print(f"Satelita:     {p['satellite']}")
        print(f"Start (AOS):  {p['aos']} UTC")
        print(f"Szczyt (TCA): {p['tca']} UTC (Max El: {p['max_elev']}°)")
        print(f"Koniec (LOS): {p['los']} UTC")
        print(f"Czas trwania: {p['duration_sec'] / 60:.1f} minut")
