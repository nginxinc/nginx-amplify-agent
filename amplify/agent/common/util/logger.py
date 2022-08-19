# -*- coding: utf-8 -*-
import logging
import logging.config

from amplify.agent.common.context import context

try:
    import thread
except ImportError:
    # Renamed in Python 3
    import _thread as thread


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"

LOGGERS_CACHE = {}


class NAASLogRecord(logging.LogRecord):
    def __init__(self, *args, **kwargs):
        logging.LogRecord.__init__(self, *args, **kwargs)
        thread_id = thread.get_ident()
        self.action_id = context.action_ids.get(thread_id, 0)


class NAASLogger(logging.getLoggerClass()):
    @staticmethod
    def makeRecord(name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None):
        return NAASLogRecord(name, level, fn, lno, msg, args, exc_info, func)


logging.setLoggerClass(NAASLogger)


def setup(logger_file):
    logging.config.fileConfig(logger_file)


def get(log_name):
    """
    Creates logger object to specified log and caches it in LOGGERS_CACHE dict

    :param log_name: log name
    :return: logger object
    """
    if log_name not in LOGGERS_CACHE:
        logger = logging.getLogger(log_name)
        LOGGERS_CACHE[log_name] = logger
    return LOGGERS_CACHE[log_name]


def get_debug_handler(log_file):
    """
    returns a file handler for debug log file
    :param log_file: str log file
    :return: FileHandler obj
    """
    handler = logging.FileHandler(log_file, 'a')
    formatter = logging.Formatter('%(asctime)s [%(process)d] %(action_id)s %(threadName)s %(message)s')
    handler.setFormatter(formatter)
    return handler
