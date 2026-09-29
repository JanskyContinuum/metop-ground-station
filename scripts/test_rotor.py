"""Read-only by default; movement and park require explicit switches."""
import argparse
import threading

from groundstation.config import load_config
from groundstation.hardware.lock import HardwareLock
from groundstation.hardware.mocks import MockRotor
from groundstation.hardware.rotor import RotorController


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config")
    parser.add_argument("--jog", action="store_true")
    parser.add_argument("--park", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    rotor = MockRotor(config.rotor) if config.mock else RotorController(config.rotor)
    stop = threading.Event()
    with HardwareLock(config.storage.root.resolve()).hold("rotor CLI test"):
        print("TCP rotctld position:", rotor.healthcheck())
        if args.jog:
            from groundstation.services.diagnostics import Diagnostics
            diagnostic = Diagnostics(config, rotor, None, None, None, stop)
            # Use the already acquired cross-process lock through a no-op adapter.
            from contextlib import nullcontext
            diagnostic.lock = type("Held", (), {"hold": lambda *args: nullcontext()})()
            print(diagnostic.run("jog"))
        if args.stop:
            rotor.stop()
            print("STOP acknowledged")
        if args.park:
            try:
                rotor.wait_for_position(rotor.park(), stop)
                print("Parked")
            finally:
                rotor.stop()


if __name__ == "__main__":
    main()
