# -*- coding: utf-8 -*-
import signal
from functools import wraps


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class TimeoutException(Exception):
    description = 'Operation exceeded time allowed'

    def __init__(self, message=None, payload=None):
        super(TimeoutException, self).__init__()
        self.message = message if message is not None else self.description
        self.payload = payload

    def __str__(self):
        return "(message=%s, payload=%s)" % (self.message, self.payload)


def timeout(seconds=10, error_message=TimeoutException.description):
    """
    Simple timeout decorator.  Not thread safe...if using multi-threading, it
    will be caught by a random thread.

    Also note, only works if logic is asynchronous.  The `signal` library can
    only check for signals or obey handlers if the GIL is returned.

    Adapted from:

    https://stackoverflow.com/questions/2281850/timeout-function-if-it-takes-too-long-to-finish

    Example usage::
        @timeout()
        def my_func():
            ...

        @timeout(1, error_message='Timed out after 1 second')
        def my_func():
            ...
    """
    def decorator(func):
        # define the handler
        def _handle_timeout(signum, frame):
            raise TimeoutException(error_message)

        @wraps(func)
        def decorated_view(*args, **kwargs):
            # set create the signal alarm
            signal.signal(signal.SIGALRM, _handle_timeout)
            # schedule an alarm
            signal.alarm(seconds)

            try:
                result = func(*args, **kwargs)
            finally:
                signal.alarm(0)  # disable the alarm

            return result
        return decorated_view
    return decorator
