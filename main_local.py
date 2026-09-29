import time
import subprocess
import os
import sys
import signal
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

    print(f"\n[!] Wybrano: {sat_name}. Oczekiwanie na start (AOS: {aos} UTC)...")

    # Pętla oczekująca na start przelotu
    while datetime.utcnow() < aos:
        time_left = (aos - datetime.utcnow()).total_seconds()
        print(f"Pozostało: {int(time_left)}s...", end="\r")
        time.sleep(2)

    print("\n[!] Przelot rozpoczęty! Rotor zaczyna śledzić...")
    print("[!] Nasłuchuję momentu wyjścia satelity zza przeszkód, by rozpocząć nagrywanie.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    baseband_file = f"capture_{sat_name.lower()}_{timestamp}.s16"
    out_dir = f"demod_{sat_name.lower()}_{timestamp}"

    recording_started = False
    recorder_process = None

    # Pętla śledzenia rotorem w trakcie przelotu
    while datetime.utcnow() < los:
        az, el = tracker.get_position(sat_name)

        if az is not None and el is not None:
            # Rotor cały czas obraca się
            rotor.set_position(az, el)

            # Odczytujemy nasz fizyczny limit (ściana/stolik) dla aktualnego azymutu
            current_min_el = 50.0 if (az < 80 or az > 270) else 30.0

            # --- LOGIKA STARTU I STOPU NAGRYWANIA ---
            if not recording_started:
                # Jeśli satelita wyszedł PONA limit - odpalamy
                if el >= current_min_el:
                    print(
                        f"\n[REC] Satelita wszedł w strefę czystego widzenia (Elewacja: {el:.1f}°). START NAGRYWANIA!")

                    # Dajemy maksa czasu do LOS, bo i tak przerwiemy to ręcznie w odpowiednim momencie
                    time_left_for_pass = (los - datetime.utcnow()).total_seconds()

                    record_cmd = [
                        "python3", "RaspberryHydraRecorder.py",
                        "--freq", "1701.3e6",
                        "--rate", "5e6",
                        "--time", str(int(time_left_for_pass + 10)),
                        "--out", baseband_file
                    ]

                    recorder_process = subprocess.Popen(record_cmd)
                    recording_started = True
            else:
                # Jeśli nagrywanie trwa, a satelita spadł PONIŻEJ limitu (chowa się za przeszkodę)
                if el < current_min_el:
                    print(f"\n[REC] Satelita schował się za przeszkodę (Elewacja: {el:.1f}°). ZATRZYMUJĘ NAGRYWANIE!")
                    # Wysyłamy sygnał przerwania bezpośrednio do procesu (odpowiednik Ctrl+C)
                    recorder_process.send_signal(signal.SIGINT)
                    # Wychodzimy z pętli śledzenia, bo dalsze patrzenie w ścianę nie ma sensu
                    break

        time.sleep(2)

    print("\n[!] Śledzenie zakończone. Powrót rotora do bazy...")
    rotor.set_position(0.0, 0.0)

    # --- SEKCJA DEMODULACJI ---
    if recording_started and recorder_process is not None:
        print("[!] Czekam na poprawne zamknięcie pliku z próbkami...")
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
                    print("[DEMOD] Plik z próbkami został poprawnie usunięty (oszczędność miejsca).")
            except Exception as e:
                print(f"[DEMOD] Błąd podczas usuwania pliku: {e}")
        else:
            print("[DEMOD] Błąd podczas demodulacji. Plik z próbkami NIE został usunięty.")
    else:
        print("\n[!] UWAGA: Satelita podczas tego przelotu nigdy nie przebił wyznaczonych limitów elewacji (30/50°).")
        print("[!] Nagrywanie w ogóle nie wystartowało.")

    print("\n[✔] Proces całkowicie zakończony!")


if __name__ == "__main__":
    main()