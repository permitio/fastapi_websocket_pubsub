import collections
import inspect
import logging
import logging.config
import logging.config
import os
import threading
import structlog
from structlog import stdlib, DropEvent

from lib.logger.base_logger_conf import DEV_LOGGING, PROD_LOGGING


def is_dev():
    return "DEV_ENV" not in os.environ  


default_log_level = "DEBUG" if is_dev() else "INFO"
log_level = os.environ.get("LOG_LEVEL", default_log_level)
LOGGING_CONFIG = DEV_LOGGING if is_dev() else PROD_LOGGING


def get_logger(logger_name):
    if logger_name is None:
        logger_name = inspect.currentframe().f_back.f_globals["__name__"]
    logging.getLogger(logger_name).setLevel(log_level)
    return structlog.wrap_logger(logging.getLogger(logger_name))


def _add_thread_info(logger, method_name, event_dict):  # pylint: disable=unused-argument
    thread = threading.current_thread()
    event_dict["thread_id"] = thread.ident
    event_dict["thread_name"] = thread.name
    return event_dict


def _order_keys(logger, method_name, event_dict):  # pylint: disable=unused-argument
    return collections.OrderedDict(sorted(event_dict.items(), key=lambda item: (item[0] != "event", item)))


def _filer_by_asset_name(logger, name, event_dict):
    if event_dict.get("assetName", "") in ASSET_LOGGINING_BLACKLIST:
        raise DropEvent
    return event_dict


logging.config.dictConfig(LOGGING_CONFIG)
processors_list = [
    # This performs the initial filtering, so we don't
    # evaluate e.g. DEBUG when unnecessary
    stdlib.filter_by_level,
    _filer_by_asset_name,
    _add_thread_info,

    # Adds logger=module_name (e.g __main__)
    # Adds level=info, debug, etc.
    structlog.stdlib.add_log_level,
    # Performs the % string interpolation as expected
    structlog.stdlib.PositionalArgumentsFormatter(True),
    # Include the stack when stack_info=True
    structlog.processors.StackInfoRenderer(),
    # Include the exception when exc_info=True
    # e.g log.exception() or log.warning(exc_info=True)'s behavior
    structlog.processors.format_exc_info,
    # Decodes the unicode values in any kv pairs
    structlog.processors.UnicodeEncoder(),
    # Creates the necessary args, kwargs for log()
]
if not is_dev():
    processors_list = processors_list + [
        structlog.stdlib.add_logger_name,
        _order_keys,
        structlog.stdlib.render_to_log_kwargs,
    ]
else:
    processors_list = processors_list + [_order_keys, structlog.dev.ConsoleRenderer(repr_native_str=True)]

structlog.configure_once(
    context_class=dict,
    logger_factory=stdlib.LoggerFactory(),
    wrapper_class=stdlib.BoundLogger,
    processors=processors_list,
)

logger = get_logger(__name__)
logger.info("logging started")
