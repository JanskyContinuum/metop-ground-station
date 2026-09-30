import argparse

from groundstation.config import load_config
from groundstation.hardware.lock import HardwareLock
from groundstation.hardware.mocks import MockSDR
from groundstation.hardware.sdr import SDRReceiver
from groundstation.services.diagnostics import Diagnostics


def main():
    parser = argparse.ArgumentParser(
        description="Probe SDRplay and record/delete a 3-second CS16 test"
    )
    parser.add_argument("--config")
    args = parser.parse_args()
    config = load_config(args.config)
    factory = MockSDR if config.mock else SDRReceiver
    diagnostics = Diagnostics(
        config, None, factory, None, HardwareLock(config.storage.root.resolve())
    )
    print(diagnostics.run("record"))


if __name__ == "__main__":
    main()
