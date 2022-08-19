# -*- coding: utf-8 -*-


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class cycle(object):
    """
    Simple circular buffer generator that doesn't require the storing of a full iterable like itertools.cycle.
    """
    def __init__(self, start=0, stop=None, step=1):
        self.start = (start - step) if stop is not None else (0 - step)
        self.stop = stop if stop is not None else start
        self.step = step

        self._current = self.start

    def __iter__(self):
        return self

    def __next__(self):
        """Python3 compatibility"""
        return self.next()

    def next(self):
        if self._current <= (self.stop - self.step):
            self._current += self.step
        else:
            self._current = self.start + self.step
        return self._current
