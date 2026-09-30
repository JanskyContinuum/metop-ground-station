# Troubleshooting

| Symptom | Check |
| --- | --- |
| Cannot open the web UI | Keep the foreground process running; use Pi 5's Ethernet IP from `hostname -I`, port 8000. Check existing LAN policy with the owner. |
| No passes | TLE warning/epoch, Internet/cache, UTC clock, station coordinates, minimum elevation, mechanical floor and horizon mask. A two-hour window can legitimately be empty. |
| Refresh appears unchanged | Requests are limited to one attempt per 15 minutes by default, including manual refresh. Existing selected passes retain their orbital snapshot. |
| Rotor host missing | Verify actual Pi Zero IP using `ip neigh`, existing NetworkManager profiles and `nc -vz <host> 4533`. Do not use the Pi 5 AP address as the rotor. |
| Movement refused | Verify mechanical range, clear swept paths and park position; explicitly set `limits_confirmed: true`. The default 50-degree floor is conservative. |
| Rotor does not settle | Check physical controller, calibration, position readback, allowed range and communication; do not change MD-02 or its services automatically. |
| Hardware busy | Tracking, diagnostics or G/T owns the shared lock. Wait or cancel that operation. Do not delete lock files while a process is running. OS releases locks after process exit. |
| SoapySDR import/device failure | Check OS Python binding, virtualenv system-site access, SDRplay API installation and Soapy SDRplay plugin with the owner. Confirm local USB receiver. |
| Bias-T unsupported | This application requires an explicitly discoverable `biastee` setting and fails rather than silently ignoring it. Verify the installed plugin/API version. |
| Overflow / stream stall | Actual sample rate, USB path, storage write speed, CPU load, gain settings and receiver API. Overflow is not treated as harmless timeout. |
| Insufficient disk | Check expected CS16 bytes and reserve; choose storage.root on a sufficiently fast local disk. Do not move full passes into RAM without explicitly provisioning it. |
| SatDump command fails | Read retained `data/work/obs-*/satdump.log`; compare installed `satdump --help` and configure `command_prefix`, pipeline and supported CS16 syntax. |
| No AVHRR image | Inspect retained products; choose an appropriate relative `satdump.image_glob`. A decoder exit code alone is not success. Corrupt/tiny/thumbnail/non-AVHRR output is rejected. |
| Failed raw remains | Expected for the configured retention period; cleanup runs while the application runs. Check `failed.json`. |
| WESIS unavailable | Check timestamp, cache, publication delay and quality flags. No valid solar-flux data means no calculated G/T. |
| Station stopped | Active recording is cancelled and the queue cleared. Use Resume scheduling once stopping is complete, then select passes again. |

The application changes no network profiles, systemd services, serial setup or
boot settings. Hardware repairs or system dependency installations require the
station owner's normal administration process.
