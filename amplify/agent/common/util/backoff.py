# -*- coding: utf-8 -*-
from random import randint


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


# Constants
EXPONENTIAL_COEFFICIENT = 2  # Exponential decay function
TIMEOUT_PERIOD = 15  # seconds
MAXIMUM_TIMEOUT = 3600  # seconds


def exponential_delay(n):
    """
    Simple algorithm that will evenly distribute agent HTTP delays such that
    overall Agent reports to backend (req/s) exponentially decay.

    :param n: Int Number of periods/fails
    :return: Int Number of seconds for agent to delay before next HTTP request.
    """
    if n < 1:
        return 0

    exponential_limit = \
        (1.0/EXPONENTIAL_COEFFICIENT) * \
        TIMEOUT_PERIOD * \
        (EXPONENTIAL_COEFFICIENT ** n)
    period_size = min(exponential_limit, MAXIMUM_TIMEOUT)

    return randint(0, period_size - 1)
