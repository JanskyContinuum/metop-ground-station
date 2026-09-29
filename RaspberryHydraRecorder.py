import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CS16
import numpy as np
import time
import sys
import argparse

class RaspberryHydraRecorder:

    CHUNK_SIZE = 131072
    CHANNEL = 0

    def __init__(self, driver_args='driver=hydrasdr'):
        """Inicjalizacja urządzenia."""
        try:
            print(f"[INIT] Szukam urządzenia: {driver_args}...")
            self.sdr = SoapySDR.Device(driver_args)
            print(f"[INIT] Połączono z: {self.sdr.getHardwareKey()}")
        except Exception as e:
            print(f"[ERROR] Nie można otworzyć urządzenia: {e}")
            sys.exit(1)

    def configure(self, frequency, sample_rate, gain):

        # wlaczanie bias tee
        if True:
            try:
                self.sdr.writeSetting("biastee", "true")
                print("[CONF] Włączono Bias-Tee (Zasilanie LNA aktywne).")
            except Exception as e:
                print(f"[WARNING] Sterownik zgłosił problem z włączeniem Bias-Tee: {e}")
        try:
            self.sdr.setSampleRate(SOAPY_SDR_RX, self.CHANNEL, sample_rate)
            self.sdr.setFrequency(SOAPY_SDR_RX, self.CHANNEL, frequency)
            self.sdr.setGain(SOAPY_SDR_RX, self.CHANNEL, gain)

            print(f"[CONF] Ustawiono: Freq={frequency / 1e6}MHz, Rate={sample_rate / 1e6}MSPS, Gain={gain}")
        except Exception as e:
            print(f"[ERROR] Błąd konfiguracji: {e}")

    def record_cs16(self, duration_sec, output_filename):
        """Nagrywa sygnał w formacie CS16."""
        rx_stream = self.sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CS16, [self.CHANNEL])
        buff = np.zeros(self.CHUNK_SIZE * 2, dtype=np.int16)

        sample_rate = self.sdr.getSampleRate(SOAPY_SDR_RX, self.CHANNEL)
        total_samples = int(sample_rate * duration_sec)


        full_path = output_filename

        print(f"[REC] Start nagrywania do: {full_path}")
        self.sdr.activateStream(rx_stream)
        time.sleep(0.1)

        samples_collected = 0

        try:
            with open(full_path, "wb") as f:
                while samples_collected < total_samples:
                    sr = self.sdr.readStream(rx_stream, [buff], self.CHUNK_SIZE, timeoutUs=100000)

                    if sr.ret > 0:
                        samples_now = sr.ret
                        if samples_collected + samples_now > total_samples:
                            samples_now = total_samples - samples_collected

                        valid_data = buff[:samples_now * 2]
                        f.write(valid_data.tobytes())
                        samples_collected += samples_now

                    elif sr.ret == -4:
                        pass  # Timeout
                    else:
                        print(f"[ERROR] Stream error code: {sr.ret}")
                        break

                    if samples_collected % (total_samples // 20) < self.CHUNK_SIZE:
                        print(".", end="", flush=True)

        except KeyboardInterrupt:
            print("\n[REC] Przerwano nagrywanie.")
        except Exception as e:
            print(f"\n[ERROR] Wystąpił błąd: {e}")
        finally:
            print("\n[REC] Zamykanie strumienia...")
            self.sdr.deactivateStream(rx_stream)
            self.sdr.closeStream(rx_stream)
            print("[REC] Gotowe.")



# GŁÓWNY PROGRAM (Odbierający argumenty z SSH)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nagrywanie bazy danych (Baseband) z Hydra SDR.")
    parser.add_argument("--freq", type=float, required=True, help="Częstotliwość w Hz (np. 137.1e6)")
    parser.add_argument("--rate", type=float, required=True, help="Sample rate w Hz (np. 2e6)")
    parser.add_argument("--time", type=int, required=True, help="Czas trwania w sekundach")
    parser.add_argument("--out", type=str, required=True, help="Pełna ścieżka do pliku wyjściowego")
    parser.add_argument("--gain", type=int, default=20, help="Wzmocnienie (domyślnie 40)")

    args = parser.parse_args()

    hydra = RaspberryHydraRecorder()
    hydra.configure(frequency=args.freq, sample_rate=args.rate, gain=args.gain)
    hydra.record_cs16(duration_sec=args.time, output_filename=args.out)
