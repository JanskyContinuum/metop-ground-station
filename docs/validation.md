# Validation record

Completed 2026-09-30 on Windows with Python 3.12 in a repository-local virtual
environment. No real rotor, SDRplay, Raspberry Pi or SatDump executable was
available. This record distinguishes software validation from hardware acceptance.

## Executed checks

| Check | Result |
| --- | --- |
| `ruff check .` | Passed, no errors |
| `pytest -q` | 62 passed, one dependency deprecation warning |
| `python -m pip check` | No broken requirements |
| `python -m groundstation --help` | Passed |
| Mock `scripts/test_rotor.py --jog --stop --park` | Position, jog/return, STOP and park passed |
| Mock `scripts/test_sdr.py` | Received 4096 simulated samples, showed both rates, removed test raw |
| `scripts/measure_gt.py --help` | Passed; real measurement intentionally not claimed |

The warning comes from the installed Starlette TestClient adapter deprecating
its httpx integration. It does not fail the tests; no warning is hidden.

Tests cover configuration validation, periodic horizon interpolation, legal
azimuth equivalents, rotor acknowledgements and safety refusal, real PyOrbital
prediction against fixed historical MetOp elements, TLE freshness/validation/
atomic replacement/fallback/rate limiting, overlapping selections, volatile
schedule, missing/expired passes, singleton lock release across threads, shared
hardware exclusion, raw size and free space, SDR MTU/actual-rate/manual-gain/
timeouts/stream errors, streaming power integration, decoder command arguments
and timeout/failure, AVHRR selection, image publication and hidden staging,
successful cleanup, failed raw retention/expiry, cancellation and latched STOP,
gallery reconstruction, web actions, numerical G/T and SFU conversion, angular
separation, and WESIS frequency/time/quality/cache handling.

## Running application and browser

Started the actual application with `GROUNDSTATION_MOCK=1 python -m groundstation`.
Used the in-app browser at `http://127.0.0.1:8000` to verify:

- Dashboard, pass table, hardware page and gallery render.
- Schedule and Cancel work through the HTML forms.
- SDR probe and 3-second test report simulated hardware and received samples.
- A browser-selected eight-second mock pass ran to `COMPLETE`.
- Its gallery folder contains exactly `avhrr.png` and `metadata.json`; the
  successful work/raw/products directory was removed.
- The image link is served successfully, and the gallery displays a simulated
  reception label.
- After restarting the application, state is `IDLE`, no selection remains, and
  the saved image is still reconstructed from disk.

![Verified mock gallery](images/mock-gallery.png)

The pytest lifecycle test separately selects a future pass before shutdown and
asserts that the replacement application has no selected passes. Failure tests
confirm raw retention independently of the successful browser demonstration.

## Live public data verification

Fetched the BKG WESIS plain-text index and real SFX files. The 2026-09-29 noon
file yielded 937 unflagged rows at the published frequencies, including 1.665 GHz.
A small source-attributed fixture is in `tests/fixtures/wesis.sfx`. The latest
late-afternoon file had low-elevation quality errors and was correctly rejected.
No HTML scraping or guessed column names are used. No actual G/T or RF result
was fabricated.

## Publication scan

The initial repository had no commits. A source credential comment was removed
before the sanitized baseline commit. Original PDFs remain outside the repo.
An exact-value scan derived the Wi-Fi secret from the external report in memory
and compared it against all 75 committed blobs present at that check, plus the
current source/documentation tree: zero matches. Values were not written into
the scanner, report or commits. There was no history rewrite.

The original binaries under `__pycache__` were removed and never committed.
Local config, data, logs and the external reports are ignored. License selection
remains with the repository owner; `LICENSE` explicitly records that no license
has been selected.

## Required on-station acceptance

1. Confirm Pi Zero's real address and TCP 4533, existing AP/LAN topology and
   rotctld availability without changing NetworkManager or system services.
2. Confirm mechanical bounds, calibration, swept-path clearance, park position,
   settling tolerance and the independent horizon mask.
3. Verify local RSP1B/SoapySDR/API compatibility, Bias-T behavior, gain, actual
   sample rate, sustained USB/disk throughput and absence of overflows.
4. Verify installed SatDump CLI/pipeline syntax, actual AVHRR product layout,
   successful RF decode, product sizes and an appropriate disk reserve.
5. Run the G/T procedure with real Sun/cold-sky measurements, valid contemporary
   WESIS data and a checked cold-sky reference.
6. Check clean shutdown and STOP latency with the real native driver/controller.

The application deliberately provides no network/service installation or
automatic MD-02 configuration. Mock validation does not establish physical
collision safety, RF performance or scientific measurement accuracy.
