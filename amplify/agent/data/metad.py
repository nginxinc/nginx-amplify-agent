# -*- coding: utf-8 -*-
import copy
from collections import defaultdict

from amplify.agent.data.abstract import CommonDataClient


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class MetadClient(CommonDataClient):
    def __init__(self, *args, **kwargs):
        # Import context as a class object to avoid circular import on statsd.  This could be refactored later.
        from amplify.agent.common.context import context
        self.context = context

        super(MetadClient, self).__init__(*args, **kwargs)

    def meta(self, data):
        self.current = data

    def flush(self):
        if self.current:
            delivery = copy.deepcopy(self.current)
            delivery.update(agent=self.context.version)
            self.current = defaultdict(dict)
            return delivery
