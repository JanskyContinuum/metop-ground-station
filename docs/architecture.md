# Architecture

```text
Laptop browser -- HTTP --> Raspberry Pi 5 (one manually started Python process)
                              |-- FastAPI + Jinja2 + plain CSS
                              |-- in-memory selections + scheduler thread
                              |-- PyOrbital + validated CelesTrak file cache
                              |-- local SoapySDR --> USB SDRplay RSP1B
                              |-- local SatDump child process
                              |-- local work files --> AVHRR filesystem gallery
                              `-- TCP 4533 --> Pi Zero / rotctld --> UART / MD-02 / SPX-02
```

No database, accounts, SSH controller, separate worker service, frontend build,
or network provisioning. Imports never open hardware. Configuration is validated
before starting; native SoapySDR and optional Astropy load only when needed.

## Lifetime and concurrency

`python -m groundstation` starts Uvicorn with one worker. A lifespan handler
loads/refreshes TLE and predicts passes, then starts the scheduler and maintenance
threads. Each new process starts with an empty selection dictionary. State and
selections are protected by a thread mutex. Do not use multiple Uvicorn workers,
hot reload, or multiple configurations against the same physical hardware.

An application file lock prevents two servers sharing a storage root. A separate
thread/file hardware lock coordinates observations and the rotor/SDR/G/T CLI
utilities. All processes controlling this station must use the same storage root.
Other programs outside this project do not participate in this lock.

The scheduler executes one observation at a time, including processing. Overlap
checks include preposition time. SatDump duration cannot be predicted; a queued
pass may expire while processing. Expired passes fail visibly rather than run late.
Selections keep their orbital snapshot across refreshes; cancel and select again
to adopt refreshed TLE. Prediction updates every minute and TLE requests are
limited to the configured retry interval, even for the refresh button.

## Observation

`WAITING -> PREPARING -> TRACKING -> PROCESSING -> COMPLETE` (or `FAILED`).
Preposition to the chosen usable window, wait for actual rotor position, record
and track concurrently, stop acquisition, park and verify position, run SatDump,
select a readable AVHRR product, publish PNG plus metadata atomically, then remove
the observation work directory. Recording does not wait on TCP rotor calls.

The visibility mask is sampled every two seconds by default; endpoints are
conservatively rounded to known valid samples. Usable duration sums all windows;
recording uses only the longest continuous window, never joins IQ across gaps.
Mechanical reachability further restricts visibility. Runtime tracking checks
the mask and mechanical limits again. No Doppler correction or zenith flip is
implemented.

Cancellation and failures stop movement rather than automatically commanding a
new park movement. STOP latches the scheduler, cancels the active operation,
clears queued passes, and prevents late tracking/jog commands. Resume is explicit.
STOP cannot guarantee physical stopping if TCP/controller communication is lost;
use the physical controller in that case. The web STOP does not override a G/T
utility running in another process; interrupt that utility in its terminal.

Shutdown signals recording cancellation, joins owned threads and terminates only
the SatDump child it started. Socket reads and SatDump shutdown are bounded.
External native driver calls can still block; this needs verification on the Pi.
Normal process shutdown cannot protect against power loss or OS SIGKILL. Owned
unfinished observation directories are marked failed on the next start, then
retained for the configured debugging interval.

## Storage

Raw space estimate is `actual_sample_rate * seconds * 4`, multiplied by a margin
plus a fixed reserve. A preliminary check uses the requested rate, and another
uses actual readback before recording. The default 2 GB reserve is also available
for products, but large real SatDump outputs may require a larger reserve.

Only `obs-*` directories directly under the configured work root are eligible for
automatic removal. Failed observations need a valid `failed.json` marker and an
expired retention timestamp. Unmarked files are preserved. Cleanup runs each
minute while the application runs, not through a system service.

The gallery is a scan of `YYYY/<reception>/metadata.json` plus `avhrr.png`.
Hidden staging directories are never displayed. Gallery is committed before any
raw removal. Mock results live under `data/mock` when started with the documented
environment variable and carry an explicit simulated flag.
