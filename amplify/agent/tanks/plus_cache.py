# -*- coding: utf-8 -*-
from collections import defaultdict, deque

from amplify.agent import Singleton


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class PlusCache(Singleton):
    """
    Cache object that accepts and maintains cached values of plus_status.  Key-value store where the keys are the plus
    status urls.
    """

    def __init__(self):
        super(PlusCache, self).__init__()
        self.caches = defaultdict(deque)

    def __getitem__(self, plus_url):
        if not self.caches[plus_url]:
            self.caches[plus_url] = deque(maxlen=3)  # Have to use this workaround to limit the length of deque.
        return self.caches[plus_url]

    def __delitem__(self, plus_url):
        del self.caches[plus_url]

    def __setitem__(self, plus_url, value):
        pass  # Disable __setitem__

    def put(self, plus_url, data):
        """
        Simple put method that appends data onto the specified deque.

        :plus_url: Str Key
        :data: Tuple (Plus Status JSON, stamp)
        """
        self.__getitem__(plus_url).append(data)

    def get_last(self, plus_url):
        if plus_url in self.caches and len(self.caches[plus_url]):
            return self.caches[plus_url][-1]
        else:
            return None, None
