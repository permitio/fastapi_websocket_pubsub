PROD_LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters":
        {
            "json": {
                "format": "%(message)s %(lineno)d %(pathname)s",
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            }
        },
    "handlers": {
        "json": {
            "class": "logging.StreamHandler",
            "formatter": "json"
        }
    },
    "loggers": {
        "": {
            "handlers": ["json"],
            "level": "INFO"
        }
    },
}

DEV_LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {
        "default": {
            "level": "DEBUG",
            "()": "logging.StreamHandler",
        }
    },
    "loggers": {
        "": {
            "handlers": ["default"],
            "level": "INFO",
            "propagate": True
        }
    },
}
