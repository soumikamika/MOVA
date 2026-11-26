import logging
import logging.config


def setup_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
                }
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "standard"}
            },
            "root": {"level": level.upper(), "handlers": ["console"]},
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
