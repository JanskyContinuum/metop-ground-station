import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CS16
import numpy as np
import time
import sys
import os

class HydraController:
    # Stałe klasowe
    CHUNK_SIZE = 4096
    CHANNEL = 0

    def __init__(self, driver_args='driver=hydrasdr'):
        """
        Inicjalizacja urządzenia.
        """
        try:
            print(f"[INIT] Szukam urządzenia: {driver_args}...")
            self.sdr = SoapySDR.Device(driver_args)
            print(f"[INIT] Połączono z: {self.sdr.getHardwareKey()}")
        except Exception as e:
            print(f"[ERROR] Nie można otworzyć urządzenia: {e}")
            sys.exit(1)

    def configure(self, frequency, sample_rate, gain):
        """
        Konfiguracja parametrów radia.
        """
        try:
            self.sdr.setSampleRate(SOAPY_SDR_RX, self.CHANNEL, sample_rate)
            self.sdr.setFrequency(SOAPY_SDR_RX, self.CHANNEL, frequency)
            self.sdr.setGain(SOAPY_SDR_RX, self.CHANNEL, gain)
            
            print(f"[CONF] Ustawiono: Freq={frequency/1e6}MHz, Rate={sample_rate/1e6}MSPS, Gain={gain}")
            
            # Próba programowego włączenia Bias-T dla wzmacniacza SAWBird
            try:
                self.sdr.writeSetting("biastee", "true")
                print("[CONF] Wysłano komendę włączenia Bias-T.")
            except:
                print("[CONF] Sterownik nie wspiera komendy 'biastee' lub jest włączony sprzętowo (zignoruj to, jeśli SAWBird świeci).")

        except Exception as e:
            print(f"[ERROR] Błąd konfiguracji: {e}")

    def record_cs16(self, duration_sec, output_filename):
        """
        Nagrywa sygnał w formacie CS16 (Complex Short 16-bit).
        """
        rx_stream = self.sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CS16, [self.CHANNEL])
        
        buff = np.zeros(self.CHUNK_SIZE * 2, dtype=np.int16)
        
        sample_rate = self.sdr.getSampleRate(SOAPY_SDR_RX, self.CHANNEL)
        total_samples = int(sample_rate * duration_sec)
        
        full_path = f"{output_filename}.s16" 
        
        print(f"[REC] Przygotowano nagrywanie do: {full_path}")
        
        # Wyraźny sygnał dla Ciebie
        print("\n" + "="*50)
        print("!!! UWAGA: ROZPOCZYNAM NAGRYWANIE PRZEZ 60 SEKUND !!!")
        print("!!! TERAZ PATRZ NA ZASILACZ / AMPEROMIERZ !!!")
        print("="*50 + "\n")

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
                        pass # Timeout
                    else:
                        print(f"[ERROR] Stream error code: {sr.ret}")
                        break
                        
                    if samples_collected % (total_samples // 20) < self.CHUNK_SIZE:
                        print(".", end="", flush=True)

        except KeyboardInterrupt:
            print("\n[REC] Przerwano nagrywanie (benchmark przerwany).")
        except Exception as e:
            print(f"\n[ERROR] Wystąpił błąd: {e}")
        finally:
            print("\n[REC] Zamykanie strumienia...")
            self.sdr.deactivateStream(rx_stream)
            self.sdr.closeStream(rx_stream)
            print("[REC] Nagrywanie zakończone.")

# ==========================================
# GŁÓWNY PROGRAM
# ==========================================

if __name__ == "__main__":

    hydra = HydraController()

    # Parametry pod MetOp-B (HRPT)
    hydra.configure(
        frequency=1701.3e6, # 1701.3 MHz
        sample_rate=6e6,    # 4 MSPS mocno obciąży procesor i USB
        gain=40             # Ustaw na tyle, ile będziesz używać w rzeczywistości
    )

    filename = "benchmark_metop"
    
    # 60 sekund nagrywania
    hydra.record_cs16(duration_sec=60, output_filename=filename)

    # Sprzątanie po benchmarku
    full_path = f"{filename}.s16"
    if os.path.exists(full_path):
        os.remove(full_path)
        print(f"\n[CLEANUP] Skasowano plik {full_path}. Karta SD bezpieczna!")
    else:
        print(f"\n[CLEANUP] Nie znaleziono pliku {full_path} do usunięcia.")
