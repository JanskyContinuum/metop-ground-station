"""Read-only by default; movement and park require explicit switches."""

import argparse
import threading

from groundstation.config import load_config
from groundstation.hardware.lock import HardwareLock
from groundstation.hardware.mocks import MockRotor
from groundstation.hardware.rotor import RotorController
from groundstation.services.diagnostics import Diagnostics


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
    diagnostic = Diagnostics(
        config, rotor, None, None, HardwareLock(config.storage.root.resolve()), stop
    )
    print(diagnostic.run("rotor"))
    for action in ("jog", "stop", "park"):
        if getattr(args, action):
            print(diagnostic.run(action))


if __name__ == "__main__":
    main()
