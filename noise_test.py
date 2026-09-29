import SoapySDR
from SoapySDR import SOAPY_SDR_RX, SOAPY_SDR_CS16
import numpy as np
import time
import argparse
import sys


# w sieci z hotspota Koło Naukowe Projektowania 1
# Historical access credentials removed.
def main():
    parser = argparse.ArgumentParser(description="Zrzut surowych próbek I/Q do analizy Noise Floor.")
    parser.add_argument("--out", type=str, required=True, help="Nazwa pliku wyjściowego (np. noise_poe.raw)")
    parser.add_argument("--freq", type=float, default=1701.3e6, help="Częstotliwość środkowa w Hz (domyślnie 1701.3 MHz)")
    parser.add_argument("--rate", type=float, default=5e6, help="Prędkość próbkowania (domyślnie 5 MSps)")
    parser.add_argument("--gain", type=int, default=20, help="Wzmocnienie LNA (stałe dla obu testów)")
    parser.add_argument("--time", type=int, default=5, help="Czas nagrywania w sekundach")
    args = parser.parse_args()

    # 1. Inicjalizacja HydraSDR
    try:
        sdr = SoapySDR.Device("driver=sdrplay")
        print(f"[*] Połączono z SDR: {sdr.getHardwareKey()}")
    except Exception as e:
        print(f"[!] Błąd połączenia z SDR: {e}")
        sys.exit(1)

    channel = 0
    sdr.setSampleRate(SOAPY_SDR_RX, channel, args.rate)

    actual_rate = sdr.getSampleRate(SOAPY_SDR_RX, channel)
    print(f"[*] Żądane próbkowanie: {args.rate / 1e6:.2f} MSps")
    print(f"[*] Rzeczywiste próbkowanie SDR: {actual_rate / 1e6:.2f} MSps")
   
    print("sample rate", sdr.getSampleRate(SOAPY_SDR_RX, channel))
    print("bandwidth", sdr.getBandwidth(SOAPY_SDR_RX, channel))
    sdr.setFrequency(SOAPY_SDR_RX, channel, args.freq)
    sdr.setGainMode(SOAPY_SDR_RX, channel, False)
    sdr.setGain(SOAPY_SDR_RX, channel, args.gain)

    
    # Wyłączenie Bias-Tee - przy pomiarze szumów z terminatorem zasilanie na port jest zbędne i niebezpieczne!
    try:
        sdr.writeSetting("biastee", "false")
    except:
        pass

    # 2. Konfiguracja strumienia CS16 (16-bit IQ)
    rx_stream = sdr.setupStream(SOAPY_SDR_RX, SOAPY_SDR_CS16, [channel])

    
    chunk_size = sdr.getStreamMTU(rx_stream)
    # Bufor na próbki (rozmiar x 2, bo I oraz Q to osobne int16)
    buff = np.zeros(chunk_size * 2, dtype=np.int16) 
    
    total_samples_to_read = int(actual_rate * args.time)
    samples_read = 0
    sdr.activateStream(rx_stream)

    print(f"[*] Rozpoczynam nagrywanie {args.time} sekund do pliku {args.out}...")
    start_time = time.time()

    # 3. Pętla zapisu
    with open(args.out, "wb") as f:
        while samples_read < total_samples_to_read:
            sr = sdr.readStream(rx_stream, [buff], chunk_size, timeoutUs=1000000)
            if sr.ret > 0:
                samples_now = sr.ret
                if samples_read + samples_now > total_samples_to_read:
                    samples_now = total_samples_to_read - samples_read

                # Zapisujemy tylko tyle, ile faktycznie odczytano (sr.ret * 2, bo I+Q)
                valid_data = buff[:sr.ret * 2]
                f.write(valid_data.tobytes())
                samples_read += samples_now
            elif sr.ret < 0:
                print(f"[!] Błąd odczytu strumienia: {sr.ret}")

    sdr.deactivateStream(rx_stream)
    sdr.closeStream(rx_stream)
    
    elapsed = time.time() - start_time
    print(f"[*] Nagrywanie zakończone. Zapisano {samples_read} próbek w {elapsed:.2f} s.")

if __name__ == "__main__":
    main()
