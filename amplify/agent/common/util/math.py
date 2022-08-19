# -*- coding: utf-8 -*-

__author__ = "Raymond Lau"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Raymond Lau"
__email__ = "raymond.lau@nginx.com"


def median(lst, presorted=False):
    """
    Returns the median of a list of float/int numbers. A lot of our median
    calculations are done on presorted data so the presorted flag can be
    set to skip unnecessary sorting.
    :param lst: list
    :param presorted: Boolean
    :return: float
    """
    if not presorted:
        sorted_lst = sorted(lst)
    else:
        sorted_lst = lst
    n = len(lst)
    if n < 1:
        return None
    if n % 2 == 1:
        return sorted_lst[n//2]
    else:
        return sum(sorted_lst[n//2-1:n//2+1])/2.0
