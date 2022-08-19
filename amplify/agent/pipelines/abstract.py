# -*- coding: utf-8 -*-


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class Pipeline(object):
    """
    Abstract object that provides a common API for passing data for parsing to collectors.  Pipelines should return
    iterables or be iterables themselves.
    """

    def __init__(self, name='pipeline'):
        self.name = name

    def __iter__(self):
        return self

    # This is a Pipeline API requirement
    def __next__(self):
        """`__next__' is the Python 3 version of 'next'"""
        pass

    def next(self):
        return self.__next__()

    # This is a Pipeline API requirement
    def stop(self):
        """As collectors stop, pipelines should too."""
        pass

    def __del__(self):
        self.stop()
