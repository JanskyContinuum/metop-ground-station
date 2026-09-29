import requests
import os
from pyorbital.orbital import Orbital
from datetime import datetime, timedelta

# --- KONFIGURACJA ---
STATION_LAT = 52.218835
STATION_LON = 21.010946
STATION_ALT = 0.120
# Używamy alternatywnego linku (supplemental), by ominąć Twoją obecną blokadę 2h
TLE_URL = "https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink&FORMAT=tle"
TEMP_FILE = "all_starlinks.txt"
OUT_FILE = "top_starlinks.txt"
TOP_N = 5


# --------------------

def get_tle_data():
    """Zwraca zawartość pliku TLE (korzysta z cache, żeby CelesTrak nas nie zbanował)"""

    # KROK 1: Jeśli mamy plik na dysku i ma w sobie Starlinki (a nie błąd), UŻYWAMY GO!
    if os.path.exists(TEMP_FILE):
        with open(TEMP_FILE, 'r') as f:
            content = f.read()
            # Upewniamy się, że to prawdziwy plik TLE (ma dużo linii)
            if "STARLINK" in content.upper() and len(content.splitlines()) > 100:
                print("[*] Używam bazy TLE zapisanej na dysku (omijam bana CelesTrak).")
                return content.splitlines()

    # KROK 2: Jeśli pliku nie ma lub jest uszkodzony, pobieramy nowy
    print(f"[*] Pobieram najświeższe dane TLE z CelesTrak...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        response = requests.get(TLE_URL, headers=headers, timeout=15)
        response.raise_for_status()
        text = response.text.replace('\r', '')

        if "has not updated since" in text or "STARLINK" not in text.upper():
            print("[-] CelesTrak nałożył blokadę (cooldown 2 godziny)!")
            return []

        # Zapisujemy nowiutki plik i go NIE USUWAMY
        with open(TEMP_FILE, 'w') as f:
            f.write(text)

        return text.splitlines()

    except Exception as e:
        print(f"[-] Błąd połączenia z serwerem: {e}")
        return []


def find_best_live_passes():
    lines = get_tle_data()

    if not lines:
        print("[-] Nie udało się pozyskać prawidłowych danych TLE. Koniec.")
        return

    print(f"[*] Pobrane TLE (Liczba linii: {len(lines)}). Składam bazę...")

    tle_data = {}
    for i in range(0, len(lines), 3):
        if i + 2 < len(lines):
            name = lines[i].strip()
            # Zachowujemy oryginalne 3 linijki wraz z enterami
            tle_data[name] = [lines[i] + '\n', lines[i + 1] + '\n', lines[i + 2] + '\n']

    now = datetime.utcnow()
    search_start = now - timedelta(minutes=15)
    valid_passes = []

    print(f"[*] Skanuję całą flotę Starlinków nad Warszawą (to zajmie chwilę)...")

    for sat_name in tle_data.keys():
        try:
            orb = Orbital(sat_name, tle_file=TEMP_FILE)
            passes = orb.get_next_passes(search_start, 2, STATION_LON, STATION_LAT, STATION_ALT, horizon=15)

            for rise_t, fall_t, peak_t in passes:
                if fall_t < now:
                    continue

                az, peak_el = orb.get_observer_look(peak_t, STATION_LON, STATION_LAT, STATION_ALT)

                valid_passes.append({
                    'name': sat_name,
                    'peak_el': peak_el,
                    'rise': rise_t,
                    'peak': peak_t,
                    'fall': fall_t
                })
        except Exception:
            continue

    valid_passes.sort(key=lambda x: x['peak_el'], reverse=True)
    top_passes = valid_passes[:TOP_N]

    if top_passes:
        print("\n" + "=" * 60)
        print(f" RANKING: TOP {len(top_passes)} PRZELOTÓW STARLINKÓW NAD WARSZAWĄ")
        print("=" * 60)

        with open(OUT_FILE, 'w') as out_f:
            for idx, p in enumerate(top_passes, 1):
                t_rise = p['rise'].strftime('%H:%M:%S')
                t_peak = p['peak'].strftime('%H:%M:%S')
                t_fall = p['fall'].strftime('%H:%M:%S')

                print(f"[{idx}] {p['name']}")
                print(f"    Max Elewacja: {p['peak_el']:.1f}°")
                print(f"    Czas (UTC): Start: {t_rise} | Szczyt: {t_peak} | Koniec: {t_fall}")
                print("-" * 60)

                out_f.writelines(tle_data[p['name']])

        print(f"\n[+] Sukces! Zapisano najświeższe dane 5 satelitów do '{OUT_FILE}'.")
        print(f"[!] Baza główna '{TEMP_FILE}' została zachowana (zapobiega banom z CelesTrak).")
    else:
        print("\n[-] W ciągu najbliższych 2h nie ma przelotów powyżej 15 stopni.")


if __name__ == "__main__":
    find_best_live_passes()