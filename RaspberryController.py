import subprocess
import logging

# wysyłanie komend do raspberry, siedzi na laptopie

class RaspberryController:
    def __init__(self, pi_ip="10.42.0.1", pi_user="<PI_USER>"):
        """
        Zdalny kontroler SDR na Raspberry Pi przez SSH.
        """
        self.pi_ip = pi_ip
        self.pi_user = pi_user

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("HydraController")
        self.logger.info(f"Zainicjowano połączenie SSH z {self.pi_user}@{self.pi_ip}")

    def run_ssh_command(self, command):
        """Wykonywanie polecenia na RPi przez SSH."""
        ssh_cmd = ["ssh", f"{self.pi_user}@{self.pi_ip}", command]
        self.logger.info(f"Wykonuję zdalnie: {command}")

        try:
            # subprocess.run czeka na wykonanie komendy
            result = subprocess.run(ssh_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.error(f"Błąd SSH: {result.stderr}")
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"Nie udało się połączyć przez SSH: {e}")
            return False


    def demodulate(self, pipeline_id, input_file, output_dir, samplerate="2e6"):
        """
        Uruchamia satdump na Raspberry Pi w celu demodulacji nagranego sygnału,
        a następnie usuwa plik wejściowy (baseband) po udanej operacji.
        """
        # 1. Demodulacja: Satdump offline processing wg dokumentacji
        demod_command = f"satdump pipeline {pipeline_id} baseband {input_file} {output_dir} --samplerate={samplerate} --baseband_format=cs16"
        self.logger.info(f"[DEMOD] Uruchamianie demodulacji w tle: satdump pipeline {pipeline_id}...")
        success = self.run_ssh_command(demod_command)

        if success:
            self.logger.info("[DEMOD] Demodulacja zakończona sukcesem!")

            # 2. Usunięcie pliku z próbkami
            self.logger.info(f"[DEMOD] Usuwanie pliku z próbkami: {input_file}...")
            rm_command = f"rm {input_file}"
            rm_success = self.run_ssh_command(rm_command)

            if rm_success:
                self.logger.info("[DEMOD] Plik z próbkami został poprawnie usunięty.")
            else:
                self.logger.error("[DEMOD] Błąd podczas usuwania pliku z próbkami.")

        else:
            self.logger.error("[DEMOD] Błąd podczas demodulacji. Plik z próbkami NIE został usunięty.")