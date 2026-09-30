# MetOp Ground Station

A small, manually started web application for a student satellite ground station.
Select upcoming MetOp passes, control a rotor and local SDRplay receiver, process
recordings with SatDump, and browse one useful AVHRR image per reception.

The laptop is only a browser. The application runs on the Raspberry Pi 5 next to
the antenna feed. **No database, accounts, Docker, frontend build, SSH recording
controller, or new system service is required.** Pass selections exist only in
memory and disappear whenever the application stops.

![Mock reception gallery](docs/images/mock-gallery.png)

## Hardware and existing network

- Raspberry Pi 5 (`antena`): Ethernet/PoE, local USB SDRplay RSP1B, local storage
  and SatDump, and the already configured dedicated Wi-Fi access point.
- Raspberry Pi Zero (`rotor`): existing Wi-Fi client and rotctld on TCP 4533,
  UART to the MD-02 controller driving an SPX-02 rotor.
- Laptop: browser access to the Pi 5's Ethernet/LAN IP.

```text
Building LAN -> Ethernet/PoE -> Pi 5 -> wlan0 dedicated Wi-Fi -> Pi Zero
                                |                              |
                         USB SDRplay RSP1B                 rotctld :4533
                                |                              |
                         local IQ + SatDump                UART / MD-02
                                |                              |
                          AVHRR gallery                       SPX-02
```

**THE APPLICATION DOES NOT CONFIGURE THIS NETWORK.** The report describes an
existing NetworkManager AP using `ipv4.method shared`, historically `10.42.0.1`.
The rotor client addresses in historical material conflict. `rotor.host` is
intentionally blank; discover the actual address. No Wi-Fi profiles, boot
configuration, MD-02 settings or existing rotctld services are modified.

Run these non-destructive checks on the real Raspberry Pi:

```bash
hostname -I
ip addr
ip neigh
nmcli connection show
nmcli device
ping -c 3 <rotor-host>
nc -vz <rotor-host> 4533
```

Optionally inspect `systemctl status <existing-rotctld-service>` on the Pi Zero
when its actual service name is known. See [network details](docs/network.md).

## Install

Use Python 3.11 or later. On the Pi, the native SoapySDR Python binding must match
its OS Python. If SoapySDR is already installed as an OS package, expose it to
the virtual environment using `--system-site-packages`:

```bash
cd ~/GroundStation
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -e '.[dev,gt]'
cp config/station.example.yaml config/station.yaml
```

This installs project dependencies into the local virtual environment. `gt` adds
Astropy, and `dev` adds pytest and Ruff; for reception only use `pip install -e .`.
On a development computer, an ordinary venv without system-site packages is fine.

Real hardware additionally needs these existing native dependencies, which pip
does not provide:

1. SoapySDR library and Python bindings ([official build guide](https://github.com/pothosware/SoapySDR/wiki/BuildGuide)).
2. SDRplay API compatible with RSP1B ([vendor downloads](https://www.sdrplay.com/downloads/)).
3. SDRplay Soapy plugin ([SoapySDRPlay3](https://github.com/pothosware/SoapySDRPlay3)).
4. Local SatDump with the `metop_ahrpt` pipeline ([official documentation](https://docs.satdump.org/)).

Inspect what is installed before asking the station owner to install anything:

```bash
python -c 'import SoapySDR; print(SoapySDR.getAPIVersion())'
SoapySDRUtil --info
SoapySDRUtil --find="driver=sdrplay"
satdump --help
```

Run hardware probes only while no other receiver application is using the SDR.
This project provides no privileged installer and installs no systemd service.
Existing SDRplay API services remain the station owner's responsibility.

## Configure

Edit the gitignored `config/station.yaml`. `GROUNDSTATION_CONFIG` or `--config`
can select another file. Paths are relative to the working directory; work and
gallery must be distinct subdirectories of `storage.root`.

Confirm before real operation:

- Station latitude, longitude, altitude and timezone; example coordinates are
  historical Warsaw values, not a new survey.
- `rotor.host` and TCP port, mechanical azimuth/elevation bounds, clear swept
  paths, calibrated position readback, safe park coordinates and settling time.
- `rotor.limits_confirmed: true` only after the physical checks. The example
  azimuth is -180..300 degrees; the conservative elevation floor is 50 degrees
  because the historical installation includes possible mechanical obstructions.
- Separate `horizon_mask` azimuth/elevation points define RF visibility. They
  never override mechanical limits. Azimuth points are unique in [0,360), with
  periodic interpolation across north.
- SDR center frequency, requested rate, manual gain and Bias-T power requirement.
  AGC defaults off; Bias-T defaults off. The example is 1701.3 MHz and 5 MS/s.
  Verify current satellite service/frequency and real receiver bandwidth.
- SatDump executable, command prefix/pipeline, storage space and retention policy.

The requested SDR rate can differ from the actual rate. The latter is read from
SoapySDR and passed to SatDump. Do not assume the historical 2.4/5/6 MS/s examples
are interchangeable.

## Run

```bash
cd ~/GroundStation
source .venv/bin/activate
python -m groundstation
```

Find the Pi 5 Ethernet address with `hostname -I`, then open
`http://<raspberry-ip>:8000` from the laptop. Keep the terminal process running.
Ctrl+C stops the scheduler and acquisition and closes owned hardware resources.
No boot service is created. Do not run multiple workers or use Uvicorn reload.

For a completely offline demonstration without rotor, SDR, SatDump or TLE access:

```bash
GROUNDSTATION_MOCK=1 python -m groundstation
```

PowerShell equivalent:

```powershell
$env:GROUNDSTATION_MOCK = '1'
python -m groundstation
```

Open `http://127.0.0.1:8000` on the development computer. Demo passes start shortly
after startup and last eight seconds. All demo images are clearly marked and
stored below `data/mock`, separate from real receptions. G/T does not manufacture
mock measurement results.

## Web interface and pass selection

- **Dashboard:** state, current and next selected pass, last hardware checks,
  TLE cache age/warnings, free disk and latest image.
- **Passes:** approximately two hours of predictions, AOS/LOS/TCA, maximum
  elevation, total/usable/recording duration and Schedule/Cancel buttons.
- **Hardware:** rotor connection/position, park, STOP, a 2-degree jog and return,
  SDR probe/3-second test, SatDump executable check and TLE refresh.
- **Gallery:** scans saved reception folders; click an image for full resolution.

Choose Schedule beside each wanted pass. Overlaps, including preposition time,
are rejected with an explanation. Cancel removes a waiting selection or cancels
the running observation. STOP clears the queue and latches the scheduler until
Resume scheduling. Dangerous operations use POST and per-process form tokens.
There are no user accounts; use this only on the trusted local station network.

TLE is validated before atomic cache replacement. Cache older than 24 hours is
refreshed, with fallback to previous valid data if the Internet fails. Old orbital
epochs are warned about separately from file age. Requests are rate limited,
including the refresh button. Predictions refresh each minute. Selections remain
RAM-only and are empty after restart. No suitable pass in a short window is normal.

## Reception and storage

```text
wait -> preposition -> track + record -> stop recording -> park
     -> local SatDump -> choose AVHRR -> publish PNG + metadata -> delete work
```

Recording uses the longest uninterrupted usable visibility window. The UI also
reports total usable time across all windows. One observation, including SatDump,
runs at once. A later selected pass can be missed if processing is still busy;
that condition is reported, not silently run concurrently.

CS16 requires approximately `sample_rate * seconds * 4` bytes. At 5 MS/s,
10 minutes is 12 GB before margins/products. The application checks space using
both requested and actual rates. Default reserve is 2 GB plus a 20% recording
margin; increase it for your SatDump output size and disk.

Temporary files:

```text
data/work/obs-<id>/
  observation.json
  capture.cs16
  satdump.log
  products/
  failed.json          # only on failure/interruption
```

Permanent result:

```text
data/gallery/2026/2026-09-29_120000_METOP-C/
  avhrr.png
  metadata.json
```

After a readable AVHRR image and metadata are safely published, the whole work
directory is removed, including raw IQ and AMSU/MHS/other temporary products.
If decoding, image selection or gallery saving fails, raw data is retained.
Failed work expires after `failed_raw_retention_hours` (24 hours by default);
cleanup occurs while the app runs. Unrelated files are never swept by retention.
An interrupted run is marked failed when the app restarts. The gallery is rebuilt
from disk without a database.

SatDump runs with argument arrays, normally:

```text
satdump pipeline metop_ahrpt baseband <raw> <products> --samplerate=<actual> --baseband_format=cs16
```

Match `satdump.command_prefix` to the installed CLI. Current documentation uses
`[pipeline]`; older releases can require `[]`. Do not select `[legacy]` unless the
installed release documents it for offline processing. The AVHRR finder prefers
valid composites in AVHRR paths, then other useful AVHRR images. Use an explicit
relative `satdump.image_glob` if local filenames differ. Decoder exit success
without a valid AVHRR image is still a failed reception.

## Hardware tests and G/T

```bash
python scripts/test_rotor.py
python scripts/test_rotor.py --jog --stop --park
python scripts/test_sdr.py
python scripts/measure_gt.py --repeats 3 --seconds 3
```

The default rotor test only reads position. Movement switches require confirmed
limits. The SDR test reports requested/actual rate, records three seconds, verifies
samples and deletes its test file. All tools share the application hardware lock.
Keep the same config/storage root for every command.

G/T uses Sun/cold-sky Y-factor with identical manual receiver settings and direct
IQ power integration, no huge recordings. It fetches and caches BKG WESIS raw
solar-flux data, checks quality/time, and reports the selected frequency separately
from the SDR frequency. See [G/T procedure and limitations](docs/gt-measurement.md)
for manual pointing, search, equation, uncertainty and output details.

## Testing and project layout

```bash
ruff check .
pytest
```

Tests use mocks, temporary directories, fake SoapySDR, a fixed historical MetOp
TLE fixture and a small public BKG SFX fixture. No test requires physical hardware.
See [validation record](docs/validation.md) for executed checks and remaining
hardware acceptance work.

```text
config/station.example.yaml
src/groundstation/
  config.py, __main__.py, logging_config.py
  orbit/       # TLE, passes, visibility and Sun
  hardware/    # TCP rotor, SoapySDR, locks and mocks
  services/    # scheduler, observation, SatDump, gallery, cleanup, G/T
  web/         # FastAPI, Jinja templates and plain CSS
scripts/       # rotor test, SDR test, G/T measurement
tests/         # hardware-independent tests and fixtures
docs/          # audit, architecture, network, G/T, troubleshooting, validation
```

[Architecture](docs/architecture.md) · [Audit/migration](docs/refactor-plan.md) ·
[Troubleshooting](docs/troubleshooting.md)

## Public repository and security

The legacy source credential comment was removed before the first commit. The
engineering PDF contains a real Wi-Fi PSK and remains outside this repository;
never publish it unredacted. Local configuration, caches, raw recordings, images,
G/T results and logs are ignored. There was no existing Git history to rewrite.
The sanitized baseline preserves historical code; production contains no legacy
SSH/Hydra implementation. Review staged files before publishing.

An open-source license has not been selected. `LICENSE` records this explicitly;
choose an appropriate license before presenting the project as open source.

The web interface is intentionally unauthenticated, for a trusted LAN only. Do
not expose it through public port forwarding. No network policy is altered by
this project. A web form token is a cross-site request defense, not authentication.

## Known limitations

Real Raspberry Pi timing, sustained SDR throughput, Bias-T setting support,
physical rotor limits/calibration, current satellite transmission availability,
actual SatDump output conventions and RF image quality need hardware acceptance.
The historical report did not establish successful AHRPT decoding. Mock success
is not proof of reception. No Doppler correction, rotor velocity planning,
zenith flip, resumable processing or persistent schedule is provided. Native
SDR driver calls can block outside Python's control. Basic G/T has no beam/disk
or atmospheric correction and depends on a valid nearby WESIS measurement.
