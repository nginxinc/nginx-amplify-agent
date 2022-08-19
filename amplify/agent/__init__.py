# -*- coding: utf-8 -*-


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class Singleton(object):
    """
    WARN: If you choose to use implied references (re-init), this object can
          still be marked for cleanup by the GC.  You must keep the reference
          counter > 0 at all times or you may have an unexpected clean up cause
          unexpected behavior.
    """
    _instance = None
    _init = True  # use this flag to skip future init calls if desirable

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(Singleton, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self._init = False