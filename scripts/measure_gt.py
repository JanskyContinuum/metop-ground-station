"""Sun/cold-sky Y-factor measurement, no raw recording or automatic AGC."""
import argparse
import json
import math
import signal
import statistics
import threading
from datetime import UTC, datetime

from groundstation.config import load_config
from groundstation.hardware.lock import HardwareLock
from groundstation.hardware.rotor import RotorController
from groundstation.hardware.sdr import SDRReceiver
from groundstation.orbit.horizon import HorizonMask
from groundstation.orbit.sun import sun_position
from groundstation.services.gt import WesisClient, calculate_gt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--sun", nargs=2, type=float, metavar=("AZ", "EL"))
    parser.add_argument("--cold", nargs=2, type=float, metavar=("AZ", "EL"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=3)
    parser.add_argument("--search-deg", type=float, default=0, help="Optional +/- local Sun grid search")
    args = parser.parse_args()
    config = load_config(args.config)
    if config.mock or config.sdr.agc:
        parser.error("G/T requires real hardware with AGC disabled")
    if args.repeats < 1 or not math.isfinite(args.seconds) or args.seconds <= 0:
        parser.error("Positive repeat count and integration duration required")
    if not math.isfinite(args.search_deg) or not 0 <= args.search_deg <= 5:
        parser.error("Search radius must be 0..5 degrees")
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    rotor = RotorController(config.rotor)
    mask = HorizonMask(config.horizon_mask)
    flux_client = WesisClient(config.gt, config.storage.root / "gt" / "wesis")
    results = []

    def point(position):
        az, el = position
        if el < config.gt.safe_elevation_deg or not mask.visible(az, el):
            raise ValueError("G/T pointing below safe elevation or local visibility mask")
        rotor.wait_for_position(rotor.set_position(az, el), stop)
        if stop.wait(config.gt.settle_seconds):
            raise InterruptedError("G/T cancelled")

    with HardwareLock(config.storage.root.resolve()).hold("G/T measurement"):
        try:
            # Fail before moving if no defensible flux reference is available.
            flux_client.get_flux(config.sdr.center_frequency_hz, datetime.now(UTC))
            with SDRReceiver(config.sdr) as receiver:
                for _ in range(args.repeats):
                    when = datetime.now(UTC)
                    sun = tuple(args.sun) if args.sun else sun_position(config.station, when)
                    point(sun)
                    if args.search_deg:
                        candidates = []
                        for da in (-args.search_deg, 0, args.search_deg):
                            for de in (-args.search_deg, 0, args.search_deg):
                                candidate = (sun[0] + da) % 360, sun[1] + de
                                point(candidate)
                                candidates.append((receiver.mean_power(args.seconds, stop), candidate))
                        sun = max(candidates)[1]
                        point(sun)
                    start_sun = datetime.now(UTC)
                    p_sun = receiver.mean_power(args.seconds, stop)
                    measured_sun = rotor.get_position()
                    cold = tuple(args.cold) if args.cold else ((sun[0] + config.gt.cold_offset_deg) % 360, sun[1])
                    separation = abs((cold[0] - sun[0] + 180) % 360 - 180)
                    if separation < 10 or abs(cold[1] - sun[1]) > 2:
                        raise ValueError("Cold sky must be separated by >=10 degrees azimuth at similar elevation (+/-2)")
                    point(cold)
                    start_cold = datetime.now(UTC)
                    p_cold = receiver.mean_power(args.seconds, stop)
                    flux = flux_client.get_flux(config.sdr.center_frequency_hz, start_sun)
                    results.append({**calculate_gt(p_sun, p_cold, config.sdr.center_frequency_hz, flux.flux_sfu),
                                    "measurement_utc": start_sun.isoformat(),
                                    "cold_measurement_utc": start_cold.isoformat(),
                                    "sun_position": measured_sun, "cold_position": rotor.get_position(),
                                    "wesis": flux.metadata(config.sdr.center_frequency_hz),
                                    "sdr": config.sdr.model_dump(), "actual_sample_rate_hz": receiver.actual_rate,
                                    "integration_seconds": args.seconds,
                                    "power_method": "mean (I^2 + Q^2), normalized int16, full bandwidth"})
        finally:
            rotor.stop()
    output = config.storage.root / "gt"
    output.mkdir(parents=True, exist_ok=True)
    values = [r["gt_linear"] for r in results]
    mean = statistics.mean(values)
    summary = {"measurements": results, "mean_gt_linear": mean,
               "std_gt_linear": statistics.stdev(values) if len(values) > 1 else 0,
               "mean_gt_db_per_k": 10 * math.log10(mean),
               "std_gt_db_per_k": statistics.stdev([r["gt_db_per_k"] for r in results]) if len(values) > 1 else 0}
    path = output / f"{datetime.now(UTC):%Y-%m-%d_%H%M%S_%f}_gt.json"
    path.write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Saved", path)


if __name__ == "__main__":
    main()
