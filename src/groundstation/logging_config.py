import logging
import time


def configure_logging():
    formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(name)s: %(message)s")
    formatter.converter = time.gmtime
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler])
