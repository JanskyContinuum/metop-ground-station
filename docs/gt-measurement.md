# Sun / cold-sky G/T measurement

Install the optional dependency with `python -m pip install -e '.[gt]'`.
Start from the same repository and configuration used by the web application:

```bash
python scripts/measure_gt.py --repeats 3 --seconds 3
python scripts/measure_gt.py --sun 180 55 --cold 220 55 --repeats 5 --seconds 5
python scripts/measure_gt.py --search-deg 0.5 --repeats 3 --seconds 3
```

The coordinates in the manual example are illustrative, not a pointing prediction.
Verify a clear swept path, the Sun's actual position and an unobstructed cold-sky
reference. The automated default uses Astropy's Sun position and an azimuth offset
at the same elevation. It rejects insufficient angular separation (including near
zenith), unsafe elevation and the local mask. Cold sky selection does not model
the Moon, Galactic background, RFI, buildings or ground spillover; the operator
must choose a suitable reference or override it.

The utility acquires the shared hardware lock. It fails if an observation or test
is active. It validates a WESIS reference before motion, waits for measured rotor
position and settling, then integrates Sun and cold-sky IQ directly in memory.
One SDR configuration stays open for all repeats. AGC is prohibited, including
when enabled in the station configuration. Gain, frequency, actual rate, Bias-T
and integration method remain identical. No raw IQ files are created. Clipping,
zero power, Y <= 1, and invalid flux cause clear failure.

Power is the mean of normalized `I² + Q²` across the full received bandwidth;
these are relative digital power units, not calibrated watts. The ratio is
dimensionless. Repeated G/T values include mean and sample standard deviation.
The dB mean is the logarithm of the linear mean; dB standard deviation is also
reported. Results include both pointing positions, UTC times, SDR settings and
the selected WESIS row. Outputs are `data/gt/<UTC>_gt.json`.

```text
Y = P_sun / P_cold = 10^((P_sun_dB - P_cold_dB) / 10)
lambda = c / SDR_frequency
G/T = 8*pi*k*(Y - 1) / (S*lambda^2)
G/T [dB/K] = 10*log10(G/T)
1 SFU = 1e-22 W/(m^2 Hz)
```

This implements the equation requested in the supplied G/T note. It does not
apply finite solar disk, beam-pattern, atmospheric, polarization mismatch or
frequency-interpolation corrections. Treat results as a basic engineering
measurement, with uncertainty from solar variability, receiver drift, RFI and
the reference-frequency difference. Repeated samples do not remove systematic
errors. The optional 3x3 local search maximizes measured power; interference can
produce a false peak.

## WESIS ingestion

Use BKG's machine-readable `wesis_sfx_files_latest.txt` index and raw `.SFX`
files, not HTML scraping or the headline F10.7 number. Cache index for 15 minutes
and immutable raw files under `data/gt/wesis`. Search nearby files, reject
nonzero quality flags, nonpositive/nonfinite values and out-of-window times.
The default time tolerance is one hour; publication is delayed and night data may
be unavailable. Offline cache works only while rows meet the same time tolerance.
No valid row means no G/T calculation.

Select the available frequency closest to the SDR frequency, then the closest
timestamp. Near 1.7013 GHz this is normally 1.665 GHz, a -36.3 MHz difference,
explicitly recorded. Use the atmospheric-corrected flux **not normalized to 1 AU**
(column 7 in the whitespace-separated row); the normalized column would remove
the actual Sun-Earth distance variation. The timestamps and frequency difference
remain in the output; no equality or interpolation is implied.

Sources: [BKG WESIS](https://wesis.bkg.bund.de/),
[raw data format](https://wesis.bkg.bund.de/doc/WERL00X_Weltraumwetter-Daten_20230510_Solar_Flux_EN.pdf),
[quality flags](https://wesis.bkg.bund.de/doc/Solar_Flux_Error_Flags_EN_preliminary.pdf).
Data attribution: Solar radio flux Wettzell, Federal Agency for Cartography and
Geodesy, DOI [10.71809/a9tp-z195](https://doi.org/10.71809/a9tp-z195).

On Ctrl+C the utility stops its measurements and rotor. It does not automatically
park after interruption. Web STOP cannot cancel a separate CLI process; use its
terminal or physical controller. The basic utility does not synthesize a mock
G/T result; pure numerical functions are tested without hardware.
