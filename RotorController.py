import socket
import logging
import time


class RotorController:
    """
    Czysty klient TCP do komunikacji z demonem rotctld (Hamlib).
    Zakłada, że rotctld działa jako usługa (systemd) na docelowym IP.
    """

    def __init__(self, host='10.42.0.147', port=4533, timeout=2.0):
        self.host = host
        self.port = port
        self.timeout = timeout

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("RotorController")
        self.logger.info(f"RotorController zainicjowany (połączenie z {self.host}:{self.port})")

    def get_position(self):
        """Pobiera aktualną pozycję rotora (Azymut, Elewacja)."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(self.timeout)
                s.connect((self.host, self.port))
                s.sendall(b"p\n")

                response = s.recv(1024).decode('utf-8').strip()
                lines = response.split('\n')

                if len(lines) >= 2:
                    azimuth = float(lines[0])
                    elevation = float(lines[1])
                    return azimuth, elevation
                else:
                    self.logger.error(f"Nieprawidłowa odpowiedź: {response}")
                    return None, None
        except Exception as e:
            self.logger.error(f"Błąd odczytu pozycji z {self.host}:{self.port} - {e}")
            return None, None

    def set_position(self, azimuth, elevation):
        """Wysyła komendę ustawienia pozycji rotora z uwzględnieniem maski horyzontu."""
        MIN_ELEVATION = 0.0
        MAX_ELEVATION = 180.0

        # Maska horyzontu, wynikajaca z wymiarów wózka i ściany labroatorium
        if azimuth < 80 or azimuth > 270:
            MIN_ELEVATION = 50

        if elevation < MIN_ELEVATION:
            self.logger.warning(f"Zbyt niska elewacja ({elevation}°). Wymuszam {MIN_ELEVATION}°")
            elevation = MIN_ELEVATION
        elif elevation > MAX_ELEVATION:
            self.logger.warning(f"Zbyt wysoka elewacja ({elevation}°). Wymuszam {MAX_ELEVATION}°")
            elevation = MAX_ELEVATION


        MIN_AZ = -180.0
        MAX_AZ = 300.0

        curr_az, curr_el = self.get_position()
        candidates = [azimuth - 360.0, azimuth, azimuth + 360.0]
        valid_candidates = [c for c in candidates if MIN_AZ <= c <= MAX_AZ]

        if not valid_candidates:
            self.logger.error(f"Azymut {azimuth}° jest poza fizycznym zasięgiem (-180 do 300)!")
            return False

        if curr_az is not None:
            best_azimuth = min(valid_candidates, key=lambda c: abs(c - curr_az))
        else:
            best_azimuth = valid_candidates[0]

        self.logger.info(f"Cel: {azimuth:.1f}°, Aktualnie: {curr_az}° -> Wysyłam: {best_azimuth:.1f}°")

        cmd = f"P {best_azimuth:.2f} {elevation:.2f}\n"

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(self.timeout)
                s.connect((self.host, self.port))
                s.sendall(cmd.encode('utf-8'))

                # Oczekujemy na 'RPRT 0' co oznacza sukces
                response = s.recv(1024).decode('utf-8').strip()
                if "RPRT 0" in response:
                    return True
                else:
                    self.logger.error(f"Błąd komendy ruchu: {response}")
                    return False
        except Exception as e:
            self.logger.error(f"Błąd wysyłania komendy na {self.host}:{self.port} - {e}")
            return False
