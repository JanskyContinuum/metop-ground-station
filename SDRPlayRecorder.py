import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CS16
import numpy as np
import time
import sys
import argparse

class SDRplayRecorder:
    CHANNEL = 0

    def __init__(self, driver_args='driver=sdrplay'):
        """Inicjalizacja urządzenia SDRplay."""
        try:
            print(f"[INIT] Szukam urządzenia: {driver_args}...")
            self.sdr = SoapySDR.Device(driver_args)
            print(f"[INIT] Połączono pomyślnie z RSP1B (SDRplay).")
        except Exception as e:
            print(f"[ERROR] Nie można otworzyć urządzenia. Czy 'sdrplay_api' działa w tle? Błąd: {e}")
            sys.exit(1)

    def configure(self, frequency, sample_rate, gain, enable_biastee=True, enable_agc=False):
        """Konfiguracja parametrów radia SDRplay."""
        try:
            self.sdr.setSampleRate(SOAPY_SDR_RX, self.CHANNEL, sample_rate)
            self.sdr.setFrequency(SOAPY_SDR_RX, self.CHANNEL, frequency)
            
            self.sdr.setGainMode(SOAPY_SDR_RX, self.CHANNEL, enable_agc)
            
            if enable_agc:
                print("[CONF] AGC WŁĄCZONE.")
            else:
                self.sdr.setGain(SOAPY_SDR_RX, self.CHANNEL, gain)
                print(f"[CONF] AGC WYŁĄCZONE. Wymuszono ręczne wzmocnienie Gain={gain}.")

            if enable_biastee:
                try:
                    self.sdr.writeSetting(SOAPY_SDR_RX, self.CHANNEL, "biastee", "true")
                    print("[CONF] Włączono Bias-Tee (Zasilanie LNA aktywne).")
                except Exception as e:
                    print(f"[WARNING] Sterownik zgłosił problem z włączeniem Bias-Tee: {e}")
            else:
                try:
                    self.sdr.writeSetting(SOAPY_SDR_RX, self.CHANNEL, "biastee", "false")
                    print("[CONF] Bias-Tee wyłączone.")
                except Exception:
                    pass

            print(f"[CONF] Podsumowanie ustawień: Freq={frequency / 1e6}MHz, Rate={sample_rate / 1e6}MSPS")
        except Exception as e:
            print(f"[ERROR] Błąd konfiguracji: {e}")

    def record_cs16(self, duration_sec, output_filename):
        """Nagrywa sygnał w formacie CS16."""
        rx_stream = self.sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CS16, [self.CHANNEL])
        
        # --- ZMIANA: Pytamy radio o preferowany rozmiar bufora (MTU) ---
        chunk_size = self.sdr.getStreamMTU(rx_stream)
        print(f"[INFO] Radio ustaliło sprzętowy rozmiar bufora (MTU) na: {chunk_size}")
        
        buff = np.zeros(chunk_size * 2, dtype=np.int16)

        sample_rate = self.sdr.getSampleRate(SOAPY_SDR_RX, self.CHANNEL)
        total_samples = int(sample_rate * duration_sec)
        full_path = output_filename

        print(f"[REC] Start nagrywania do: {full_path}")
        self.sdr.activateStream(rx_stream)
        
        # Dajemy radiu nieco więcej czasu na stabilizację strumienia
        time.sleep(0.5)

        samples_collected = 0

        try:
            with open(full_path, "wb") as f:
                while samples_collected < total_samples:
                    # Używamy chunk_size z radia i podnosimy timeout do 1 sekundy (1000000 us)
                    sr = self.sdr.readStream(rx_stream, [buff], chunk_size, timeoutUs=1000000)

                    if sr.ret > 0:
                        samples_now = sr.ret
                        if samples_collected + samples_now > total_samples:
                            samples_now = total_samples - samples_collected

                        valid_data = buff[:samples_now * 2]
                        f.write(valid_data.tobytes())
                        samples_collected += samples_now

                    # Niektóre wersje API SDRplay potrafią zwrócić -1 jako normalny "timeout" zanim zaczną lecieć dane
                    elif sr.ret == -1 or sr.ret == -4:
                        pass
                    else:
                        print(f"[ERROR] Krytyczny błąd strumienia: {sr.ret}")
                        break

                    # Rysowanie kropek postępu
                    if samples_collected % (total_samples // 20) < chunk_size and samples_collected > 0:
                        print(".", end="", flush=True)

        except KeyboardInterrupt:
            print("\n[REC] Przerwano nagrywanie (Otrzymano sygnał SIGINT z głównego skryptu).")
        except Exception as e:
            print(f"\n[ERROR] Wystąpił błąd podczas zrzutu na dysk: {e}")
        finally:
            print("\n[REC] Zamykanie strumienia i wyłączanie radia SDRplay...")
            self.sdr.deactivateStream(rx_stream)
            self.sdr.closeStream(rx_stream)
            print("[REC] Gotowe.")

# ==========================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nagrywanie basebandu dla SDRplay RSP1B.")
    parser.add_argument("--freq", type=float, required=True, help="Częstotliwość w Hz (np. 137.1e6)")
    parser.add_argument("--rate", type=float, required=True, help="Sample rate w Hz (np. 2e6)")
    parser.add_argument("--time", type=int, required=True, help="Czas trwania w sekundach")
    parser.add_argument("--out", type=str, required=True, help="Pełna ścieżka do pliku wyjściowego")
    parser.add_argument("--gain", type=int, default=40, help="Wzmocnienie ręczne (domyślnie 40)")
    
    parser.add_argument("--no-biastee", action="store_false", dest="biastee", help="Wyłącz Bias-Tee (domyślnie włączone)")
    parser.add_argument("--agc", action="store_true", dest="agc", help="Włącz AGC (domyślnie WYŁĄCZONE dla satelitów)")

    args = parser.parse_args()

    sdr_recorder = SDRplayRecorder()
    sdr_recorder.configure(
        frequency=args.freq, 
        sample_rate=args.rate, 
        gain=args.gain, 
        enable_biastee=args.biastee, 
        enable_agc=args.agc
    )
    sdr_recorder.record_cs16(duration_sec=args.time, output_filename=args.out)