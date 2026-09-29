import time
import subprocess
import os
import sys
from datetime import datetime
# Dodanie folderu nadrzędnego (głównego katalogu projektu) do ścieżek Pythona
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)
from SatelliteTracker import SatelliteTracker
from RotorController import RotorController

# --- KONFIGURACJA ---
STATION_LAT = 52.218835
STATION_LON = 21.010946
STATION_ALT = 120.0
TARGET_SATS = ["METOP-B", "METOP-C"]
ROTOR_PORT = '/dev/ttyUSB0'  # Upewnij się, że to właściwy port rotora na Linuxie


# --------------------

def print_menu(passes):
    print("\n" + "=" * 50)
    print(" DOSTĘPNE PRZELOTY (MIN. 50° ELEWACJI)")
    print("=" * 50)
    for idx, p in enumerate(passes):
        print(f"[{idx}] {p['satellite']}")
        print(f"    AOS (Start): {p['aos'].strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"    Max Elewacja: {p['max_elev']}°")
        print(f"    Czas trwania: {p['duration_sec'] / 60:.1f} min")
        print("-" * 50)

    print("UPEWNIJ SIE ZE POBRALES NOWE TLE ALBO JEST AUTOMATYCZNIE SIE TO DZIEJE")


def main():
    tracker = SatelliteTracker(STATION_LAT, STATION_LON, STATION_ALT)
    rotor = RotorController(serial_port=ROTOR_PORT)

    all_passes = []
    for sat in TARGET_SATS:
        sat_passes = tracker.get_good_passes(sat, hours=24, min_elevation=50.0)
        all_passes.extend(sat_passes)

    # Sortowanie chronologicznie
    all_passes = sorted(all_passes, key=lambda k: k['aos'])

    if not all_passes:
        print("Brak dobrych przelotów w ciągu najbliższych 24h.")
        return

    print_menu(all_passes)

    try:
        choice = int(input("\nWybierz numer przelotu do śledzenia: "))
        if choice < 0 or choice >= len(all_passes):
            print("Nieprawidłowy wybór.")
            return
    except ValueError:
        print("To nie jest liczba.")
        return

    selected_pass = all_passes[choice]
    sat_name = selected_pass['satellite']
    aos = selected_pass['aos']
    los = selected_pass['los']
    duration = selected_pass['duration_sec']

    print(f"\n[!] Wybrano: {sat_name}. Oczekiwanie na start (AOS: {aos} UTC)...")

    # Pętla oczekująca na przelot
    while datetime.utcnow() < aos:
        time_left = (aos - datetime.utcnow()).total_seconds()
        print(f"Pozostało: {int(time_left)}s...", end="\r")
        time.sleep(10)

    print("\n[!] Przelot rozpoczęty! Rozpoczynam śledzenie i nagrywanie...")

    # 1. Lokalne odpalenie nagrywania w tle
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    baseband_file = f"capture_{sat_name.lower()}_{timestamp}.s16"
    out_dir = f"demod_{sat_name.lower()}_{timestamp}"

    # Komenda wywołująca lokalny skrypt nagrywający
    record_cmd = [
        "python3", "RaspberryHydraRecorder.py",
        "--freq", "1701.3e6",
        "--rate", "5e6",
        "--time", str(int(duration + 10)),
        "--out", baseband_file
    ]

    # Uruchamiamy nagrywanie jako proces w tle (nie blokuje pętli rotora)
    recorder_process = subprocess.Popen(record_cmd)

    # Pętla śledzenia rotorem w trakcie przelotu
    while datetime.utcnow() < los:
        az, el = tracker.get_position(sat_name)
        if az is not None and el is not None:
            rotor.set_position(az, el)

        time.sleep(2)

    print("\n[!] Przelot zakończony (LOS). Powrót rotora do bazy...")
    rotor.set_position(0.0, 0.0)

    # Czekamy ułamek sekundy, aby upewnić się, że skrypt nagrywający zrzucił bufory
    recorder_process.wait()

    print("[!] Uruchamiam proces demodulacji lokalnie...")
    pipeline_id = "metop_ahrpt"

    demod_cmd = [
        "satdump", "pipeline", pipeline_id,
        "baseband", baseband_file,
        out_dir,
        "--samplerate=5000000",
        "--baseband_format=cs16"
    ]

    print(f"[DEMOD] Wykonuję komendę: {' '.join(demod_cmd)}")
    demod_result = subprocess.run(demod_cmd)

    if demod_result.returncode == 0:
        print("[DEMOD] Demodulacja zakończona sukcesem!")
        print(f"[DEMOD] Usuwanie pliku z próbkami: {baseband_file}...")
        try:
            if os.path.exists(baseband_file):
                os.remove(baseband_file)
                print("[DEMOD] Plik z próbkami został poprawnie usunięty.")
        except Exception as e:
            print(f"[DEMOD] Błąd podczas usuwania pliku: {e}")
    else:
        print("[DEMOD] Błąd podczas demodulacji. Plik z próbkami NIE został usunięty.")

    print("\n[✔] Proces całkowicie zakończony!")


if __name__ == "__main__":
    main()
