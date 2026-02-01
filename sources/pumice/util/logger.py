import logging
import sys
from os import getcwd
from pathlib import Path


class LogLevel:
    Debug = 'debug'
    Info = 'info'
    Warning = 'warning'
    Error = 'error'
    Critical = 'critical'

    Levels = [Debug, Info, Warning, Error, Critical]


def get_logger(name: str, level: str = LogLevel.Info):
    logger = logging.getLogger(name)

    datefmt = '%Y-%m-%d %H:%M:%S'

    # Stream handler
    # yapf: disable
    stream_format = str(
        '[%(asctime)s.%(msecs)03d]'
        '[%(levelname)-8s]'
        '[%(name)-8s]'
        '[%(filename)s:%(lineno)-d] '
        '%(message)s'
    )
    # yapf: enable

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter(stream_format, datefmt=datefmt))

    logger.addHandler(stream_handler)

    logger.setLevel(level.upper())

    return logger
