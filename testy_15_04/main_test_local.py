import sys
import time
import subprocess
import os
# Dodanie folderu nadrzędnego (głównego katalogu projektu) do ścieżek Pythona
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

from datetime import datetime
from RotorController import RotorController

# --- KONFIGURACJA TESTOWA ---
ROTOR_PORT = '/dev/ttyUSB0'  # Port rotora na laptopie Linuxowym


# ----------------------------

def main_test_local():
    print("=" * 50)
    print(" ROZPOCZĘCIE LOKALNYCH TESTÓW SYSTEMU")
    print("=" * 50)

    # 1. TEST ROTORA
    print("\n[1] TEST ROTORA...")
    rotor = RotorController(serial_port=ROTOR_PORT)

    az, el = rotor.get_position()

    if az is not None and el is not None:
        print(f"[✔] Pomyślnie odczytano pozycję. Obecny Azymut: {az}°, Elewacja: {el}°")

        new_az = (az + 3.0) % 360.0
        print(f"[*] Próba obrotu rotora w azymucie o 3 stopnie (cel: {new_az}°)...")

        success = rotor.set_position(new_az, el)
        if success:
            print("[✔] Komenda ruchu wysłana pomyślnie. Czekam 3 sekundy na obrót...")
            time.sleep(3)
            check_az, check_el = rotor.get_position()
            print(f"[*] Aktualna pozycja po teście: Azymut: {check_az}°, Elewacja: {check_el}°")
        else:
            print("[ERROR] Nie udało się wysłać komendy ruchu rotora.")
    else:
        print("[ERROR] Nie udało się odczytać pozycji z rotora. Sprawdź połączenie i port!")

    # 2. TEST LOKALNEGO SDR (HYDRA)
    
    print("\n[2] TEST NAGRYWANIA LOKALNEGO SDR...")

    timestamp = datetime.now().strftime("%H%M%S")
    test_file = f"test_capture_{timestamp}.s16"
    test_duration = 2

    record_cmd = [
        "python3", "RaspberryHydraRecorder.py",
        "--freq", "137.1e6",
        "--rate", "2e6",
        "--time", str(test_duration),
        "--out", test_file
    ]

    print(f"[*] Rozpoczynam nagrywanie na {test_duration} sekundy...")
    start_time = time.time()

    # Wywołujemy nagrywanie synchronicznie (czekamy aż skończy)
    result = subprocess.run(record_cmd)
    end_time = time.time()

    if result.returncode == 0:
        print(f"[✔] Skrypt nagrywający zakończył się sukcesem w czasie {end_time - start_time:.1f} sek.")

        # Sprawdzenie pliku na dysku
        if os.path.exists(test_file):
            size_mb = os.path.getsize(test_file) / (1024 * 1024)
            print(f"[✔] Utworzono plik: {test_file} (Rozmiar: {size_mb:.2f} MB)")

            # W ramach czyszczenia testu usuwamy plik
            os.remove(test_file)
            print("[*] Plik testowy został usunięty.")
        else:
            print("[ERROR] Skrypt się wykonał, ale plik nie został utworzony!")
    else:
        print(f"[ERROR] Błąd podczas nagrywania. Kod błędu: {result.returncode}")

    print("\n" + "=" * 50)
    print(" KONIEC TESTÓW")
    print("=" * 50)


if __name__ == "__main__":
    main_test_local()
