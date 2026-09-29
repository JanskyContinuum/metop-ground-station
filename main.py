import time
import subprocess
import os
import sys
from datetime import datetime
from SatelliteTracker import SatelliteTracker
from RotorController import RotorController
from RaspberryController import RaspberryController

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

# --- KONFIGURACJA ---
STATION_LAT = 52.218835
STATION_LON = 21.010946
STATION_ALT = 120.0
PI_IP = "10.42.0.1"  # IP głównego Raspberry
PI_USER = "<PI_USER>"  # Nazwa uzytkownika na raspberry (dla 4 - knpa, dla 5 - pi)
TARGET_SATS = ["METOP-B", "METOP-C"]


# --------------------

def print_menu(passes):
    print("\n" + "=" * 50)
    print(
        " DOSTĘPNE PRZELOTY (MIN. 50° ELEWACJI)")
    print("=" * 50)
    for idx, p in enumerate(passes):
        print(f"[{idx}] {p['satellite']}")
        print(f"    AOS (Start): {p['aos'].strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"    Max Elewacja: {p['max_elev']}°")
        print(f"    Czas trwania: {p['duration_sec'] / 60:.1f} min")
        print("-" * 50)

    print("UPEWNIJ SIĘ, ŻE POBRAŁEŚ NOWE TLE (ALBO DZIEJE SIĘ TO AUTOMATYCZNIE)")


def main():
    tracker = SatelliteTracker(STATION_LAT, STATION_LON, STATION_ALT)

    # Inicjalizacja kontrolerów
    rotor = RotorController(host=PI_IP, port=4533)
    raspi = RaspberryController(pi_ip=PI_IP, pi_user=PI_USER)

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

    # --- PĘTLA 1: oczekiwanie na przelot ---
    countdown_tick = time.time() + 1.0
    while datetime.utcnow() < aos:
        time_left = (aos - datetime.utcnow()).total_seconds()
        print(f"Pozostało: {int(time_left)}s...    ", end="\r")

        now = time.time()
        sleep_duration = countdown_tick - now
        if sleep_duration > 0:
            time.sleep(sleep_duration)
        else:
            countdown_tick = time.time()
        countdown_tick += 1.0

    print("\n\n[!] Przelot rozpoczęty! Rotor zaczyna śledzić...")
    print("[!] Nasłuchuję momentu wyjścia satelity zza przeszkód, by rozpocząć zdalne nagrywanie.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    script_path = f"/home/{PI_USER}/RepoGS_Slowinski/GroundStation/RaspberyyHydraRecorder.py"
    baseband_file = f"/home/{PI_USER}/capture_{sat_name.lower()}_{timestamp}.s16"
    out_dir = f"/home/{PI_USER}/demod_{sat_name.lower()}_{timestamp}"

    recording_started = False
    recorder_process = None

    # --- PĘTLA 2: Śledzenie z czasem bezwzględnym ---
    UPDATE_INTERVAL = 2.0
    next_tick = time.time() + UPDATE_INTERVAL

    while datetime.utcnow() < los:
        az, el = tracker.get_position(sat_name)

        if az is not None and el is not None:
            # Rotor cały czas obraca się
            rotor.set_position(az, el)

            # fizyczny limit (ściana/stolik) dla aktualnego azymutu
            current_min_el = 50.0 if (az < 80 or az > 270) else 30.0

            # --- LOGIKA STARTU I STOPU NAGRYWANIA ---
            if not recording_started:
                # Jeśli satelita wyszedł PONAD limit
                if el >= current_min_el:
                    print(
                        f"\n[REC] Satelita wszedł w strefę czystego widzenia (Elewacja: {el:.1f}°). START NAGRYWANIA NA RASPBERRY!")

                    time_left_for_pass = (los - datetime.utcnow()).total_seconds()


                    record_cmd = [
                        "ssh", f"{PI_USER}@{PI_IP}",
                        f"python3 {script_path} --freq 1701.3e6 --rate 5e6 --time {int(time_left_for_pass + 10)} --out {baseband_file}"
                    ]


                    recorder_process = subprocess.Popen(record_cmd)
                    recording_started = True
            else:
                # Jeśli nagrywanie trwa, a satelita spadł PONIŻEJ limitu
                if el < current_min_el:
                    print(
                        f"\n[REC] Satelita schował się za przeszkodę (Elewacja: {el:.1f}°). ZATRZYMUJĘ ZDALNE NAGRYWANIE!")
                    # pkill koniec nagrywania
                    subprocess.run(["ssh", f"{PI_USER}@{PI_IP}", "pkill -SIGINT -f RaspberryHydraRecorder.py"])
                    break

        # --- ABSOLUTE TIME ---
        now = time.time()
        sleep_duration = next_tick - now

        if sleep_duration > 0:
            time.sleep(sleep_duration)
        else:
            overtime = UPDATE_INTERVAL - sleep_duration
            print(
                f"\n[!] OSTRZEŻENIE: Pętla nie wyrobiła się w czasie (opóźnienie: {overtime:.2f}s). Gubimy ułamek sekundy!")
            next_tick = time.time()

        next_tick += UPDATE_INTERVAL

    print("\n[!] Śledzenie zakończone. Powrót rotora do bazy...")
    rotor.set_position(0.0, 0.0)

    # demodulacja
    if recording_started and recorder_process is not None:
        print("[!] Czekam na poprawne zamknięcie zdalnego pliku z próbkami...")
        recorder_process.wait()

        print("[!] Uruchamiam proces demodulacji na Raspberry Pi...")
        pipeline_id = "metop_ahrpt"


        raspi.demodulate(
            pipeline_id=pipeline_id,
            input_file=baseband_file,
            output_dir=out_dir,
            samplerate="5e6"
        )
    else:
        print("\n[!] UWAGA: Satelita podczas tego przelotu nigdy nie przebił wyznaczonych limitów elewacji (30/50°).")
        print("[!] Nagrywanie w ogóle nie wystartowało.")

    print("\n[✔] Proces całkowicie zakończony!")


if __name__ == "__main__":
    main()