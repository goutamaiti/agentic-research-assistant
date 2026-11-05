"""Application logging setup.

Logs carry operational metadata only. Never log API keys or document contents.
"""

from __future__ import annotations

import logging
import logging.config

LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure root and uvicorn loggers with a single consistent format."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"default": {"format": LOG_FORMAT}},
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "default"},
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                "uvicorn": {"level": level},
                "uvicorn.access": {"level": level},
                # Third-party libraries that are chatty at INFO.
                "chromadb": {"level": "WARNING"},
                "httpx": {"level": "WARNING"},
                "httpx2": {"level": "WARNING"},
            },
        }
    )
