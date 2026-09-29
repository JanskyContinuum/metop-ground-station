import argparse

import uvicorn

from groundstation.config import load_config
from groundstation.logging_config import configure_logging
from groundstation.web.app import create_app


def main():
    parser = argparse.ArgumentParser(description="Manually started local ground station")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    configure_logging()
    config = load_config(args.config)
    uvicorn.run(create_app(config), host=config.web.host, port=config.web.port, workers=1)


if __name__ == "__main__":
    main()
