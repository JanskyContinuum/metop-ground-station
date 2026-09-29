import time
from datetime import datetime
from RotorController import RotorController
from RaspberryController import RaspberryController
import subprocess

# --- KONFIGURACJA TESTOWA ---
# dane RPi Zero przy sterowniku
ROTOR_PORT = '/dev/serial0'
PI_IP = "192.168.43.224"
PI_USER = "<PI_USER>"

# ----------------------------

def main_test():
    '''
 # 1. TEST ROTORA
    print("\n[1] TEST ROTORA...")
    rotor = RotorController(host=PI_IP, port=4533)
    # Pobranie aktualnej pozycji
    az, el = rotor.get_position()

    if az is not None and el is not None:
        print(f"[✔] Pomyślnie odczytano pozycję. Obecny Azymut: {az}°, Elewacja: {el}°")

        # Ograniczenie azymutu, żeby nie przekroczyć 360 przy dodawaniu 3 stopni
        new_az = (az + 3.0) % 360.0
        # new_az = 82
        print(f"[*] Próba obrotu rotora w azymucie o 3 stopnie (cel: {new_az}°)...")

       	success = rotor.set_position(new_az, el)
        if success:
            print("[✔] Komenda ruchu wysłana pomyślnie. Czekam 3 sekundy na obrót...")
            time.sleep(3)
            # Weryfikacja nowej pozycji
            check_az, check_el = rotor.get_position()
            print(f"[*] Aktualna pozycja po teście: Azymut: {check_az}°, Elewacja: {check_el}°")
        else:
            print("[ERROR] Nie udało się wysłać komendy ruchu rotora.")
    else:
        print("[ERROR] Nie udało się odczytać pozycji z rotora. Sprawdź połączenie i port!")

    # Zatrzymanie rotora dla bezpieczeństwa
    try:
        rotor.stop()
        print("zatrzymano")
    except Exception:
        pass

'''
    # 2. TEST RASPBERRY PI I SDRPLAY
    print("\n[2] TEST POŁĄCZENIA SSH I NAGRYWANIA SDR...")
    raspi = RaspberryController(pi_ip=PI_IP, pi_user=PI_USER)

    # Przygotowanie nazwy pliku na RAM Dysku (/dev/shm) żeby nie męczyć karty SD podczas testów
    timestamp = datetime.now().strftime("%H%M%S")
    test_file = f"/dev/shm/test_capture_{timestamp}.s16"
    test_duration = 3

    # Ścieżka do skryptu (zmienione na SDRplayRecorder)
    script_path = f"/home/{PI_USER}/Desktop/RepoGS_Slowinski/GroundStation/RaspberryHydraRecorder.py"
    record_command = f"python3 {script_path} --freq 137.1e6 --rate 2e6 --time {test_duration} --out {test_file}"

    print(f"[*] Wysyłanie komendy nagrywania na {test_duration} sekundy...")
    print(f"    (Jeśli nie masz ustawionych kluczy SSH, za chwilę musisz podać hasło w terminalu)")

    start_time = time.time()
    ssh_success = raspi.run_ssh_command(record_command)
    end_time = time.time()

    if ssh_success:
        print(f"[✔] Skrypt na Malince zakończył się sukcesem w czasie {end_time - start_time:.1f} sek.")
        
        # Tworzymy komendę weryfikującą rozmiar pliku na Malince i od razu go usuwającą
        verify_and_clean_cmd = (
            f"if [ -f {test_file} ]; then "
            f"SIZE=$(stat -c%s {test_file} | awk '{{printf \"%.2f\", $1/1048576}}'); "
            f"echo '[✔] Utworzono plik: {test_file} (Rozmiar: '$SIZE' MB)'; "
            f"rm {test_file}; "
            f"echo '[*] Plik testowy został usunięty.'; "
            f"else echo '[ERROR] Skrypt się wykonał, ale plik nie został utworzony na Raspberry!'; fi"
        )
        
        print("[*] Oczekiwanie na weryfikację i usunięcie pliku na zdalnej maszynie...")
        subprocess.run(["ssh", f"{PI_USER}@{PI_IP}", verify_and_clean_cmd])

    else:
        print("[ERROR] Błąd podczas wykonywania skryptu nagrywającego na Raspberry Pi.")
        print(f"        Upewnij się, że skrypt '{script_path}' istnieje na RPi.")

    print("\n" + "=" * 50)
    print(" KONIEC TESTÓW")
    print("=" * 50)


if __name__ == "__main__":
    main_test()
