# Legacy audit and migration record

Audit date: 2026-09-29. Initial status: all files untracked; Git log: no commits.
No pre-existing history contains secrets in this repository. Both original PDFs
remain outside the repository and must not be published without sanitization.

All 16 Python files, README, gitignore, command notes, TLE files, the 12-page
engineering report and four scanned G/T pages were reviewed. The G/T note is an
AI conversation export; its speculative parser is replaced by BKG's documented
raw format. The requested equation is implemented with stated limitations.

## Complete original inventory

| Files | Classification and migration |
| --- | --- |
| SDRPlayRecorder.py | Useful CS16/MTU/manual gain reference; rewrite errors/cleanup |
| noise_test.py | Useful actual-rate readback; experimental; credential comment removed |
| RotorController.py | Useful TCP/azimuth selection; split mechanics from visibility |
| SatelliteTracker.py | Useful PyOrbital and altitude conversion; replace TLE/naive UTC |
| main.py | Obsolete SSH, hardcoded paths, broad process killing; replace |
| main_local.py | Broken serial constructor, obsolete Hydra pipeline; replace |
| main_test.py | Experimental SSH and commented rotor test; remove |
| main_test_local.py | Experimental conflicting subnet and commented SDR code; remove |
| RaspberryController.py | Obsolete SSH orchestration and remote deletion; remove |
| RaspberryHydraRecorder.py | Obsolete receiver, library sys.exit; remove |
| PowerBenchmark.py | Experimental Hydra benchmark and bare except; remove |
| track_test.py | Experimental monkey patch and broken constructor; remove |
| analiza.py | Experimental historical plots, fixed UTC+2; remove |
| testy_15_04/find_satellite.py | Experimental Starlink search; remove |
| testy_15_04/main_local.py | Duplicate obsolete Hydra/serial main; remove |
| testy_15_04/main_test_local.py | Duplicate obsolete tests; remove |
| kom.txt | SatDump 2.4 MS/s command reference; discard package removal command |
| README.md | Generic GitLab template and personal URL; replace |
| .gitignore | Only ignored analysis files; replace |
| weather.txt, starlink.txt, metop_b_history.txt | Old TLE data; replace validated cache |
| testy_15_04/all_starlinks.txt, target.txt, top_starlinks.txt | Experimental TLE data; remove |
| __pycache__/*.pyc (9 files) | Generated potentially sensitive binaries; never commit |

## Security and hardware findings

A credential-like value was present in a source comment; the external report
contains a real Wi-Fi PSK. Remove source credentials before staging; sanitize
historical usernames and personal repository URLs. No credential values belong
in this record. History is not rewritten.

The report confirms Pi 5 `antena`, Ethernet/PoE, NetworkManager
`ipv4.method shared`, historical AP `10.42.0.1`; Pi Zero `rotor`, UART to MD-02,
rotctld TCP 4533. Its client `10.142.0.147` conflicts with code's `10.42.0.147`
and old `192.168.43.*` values. Leave rotor host blank pending hardware discovery.

Legacy bounds are azimuth -180..300, elevation 0..180. Code forces 50-degree
elevation outside azimuth 80..270, while recording uses 30 degrees inside. The
report describes collision avoidance as well as obstruction. Use a conservative
global mechanical floor of 50 degrees until verified; keep a separate 30/50
visibility mask and require explicit configuration confirmation before motion.
Software bounds cannot establish that swept paths are clear.

Historical coordinates: 52.218835 N, 21.010946 E, altitude 120 m. Rates vary
between 2 MS/s tests, 2.4 MS/s command note, 5 MS/s passes, 6 MS/s benchmark.
Use configurable 5 MS/s as an example; actual readback goes to SatDump.
The report explicitly says successful RF decoding had not yet been achieved.

Other defects: shell strings passed through SSH, pkill, bare except, library
sys.exit, swallowed errors, global urllib/Starlink monkey patches, commented
implementations, unvalidated TLE, unbounded stream timeouts, naive datetime and
fixed timezone offsets. No such architecture is retained.

## Implementation plan

One manually started FastAPI process, a simple scheduler thread, one observation
at a time. Selected passes and state exist only in RAM. Local SDR/SatDump,
TCP rotor, validated file caches, atomic PNG/metadata gallery publication before
raw deletion, scoped failed-work retention. Cross-process file lock and thread
lock prevent CLI/web hardware conflicts. Offline mock mode labels its products.
No network, service, boot or MD-02 changes; no database or permanent legacy tree.
