# -*- coding: utf-8 -*-

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class StringFile(object):
    """
    Extension for StringIO that adds the 'readline()' and 'iter' facilities.
    This was originally created in order to read and manipulate files in memory
    before passing to ConfigParser.ConfigParser() objects.
    """
    def __init__(self, buffer=None):
        self._buffer = StringIO(buffer) if buffer is not None else StringIO()
        self._lines_buffer = []
        self._iter = None

        if buffer is not None:
            self._split_buffer()

    # re-implement StringIO methods
    def getvalue(self):
        return self._buffer.getvalue()

    def write(self, input):
        return self._buffer.write(input)

    def close(self):
        self._buffer.close()

    def __repr__(self):
        return str(self._buffer.getvalue())

    def __str__(self):
        return self.__repr__()

    # extending StringIO with line handlers
    def _split_buffer(self):
        # split the StringIO buffer into lines
        self._lines_buffer = self.getvalue().split('\n')

        # reset _iter cache
        self._iter = None

    def __iter__(self):
        # split the current buffer and return self for iteration
        self._split_buffer()

        # return self for iteration
        return iter(self._lines_buffer)

    def __len__(self):
        self._split_buffer()
        return len(self._lines_buffer)

    def __getitem__(self, key):
        self._split_buffer()
        return self._lines_buffer.__getitem__(key)

    def __setitem__(self, key, value):
        self._split_buffer()
        return self._lines_buffer.__setitem__(key, value)

    def __delitem__(self, key):
        self._split_buffer()
        return self._lines_buffer.__delitem__(key)

    # context manager wrapper
    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self._buffer.close()

    # breakdown helper
    def __del__(self):
        # make sure that StringIO is closed during GC collect.  This may or may
        # not happen...but since StringIO is an in memory, file-like object it
        # shouldn't matter if it is formally closed during interpreter quit.
        # We just want to make sure a close occurs during normal runtime
        # execution.
        self._buffer.close()

    # file property handlers
    def readline(self):
        if self._iter is None:
            self._iter = iter(self)

        return next(self._iter)

    def readlines(self):
        self._split_buffer()
        return self._lines_buffer
