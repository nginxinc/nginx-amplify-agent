# -*- coding: utf-8 -*-
import copy
import time

from amplify.agent.data.abstract import CommonDataClient

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"

DEFAULT_RESEND_WAIT_TIME = 4 * 60 * 60  # 4 hours


class ConfigdClient(CommonDataClient):
    def __init__(self, *args, **kwargs):
        # Import context as a class object to avoid circular import on statsd.  This could be refactored later.
        from amplify.agent.common.context import context
        self.context = context

        # Remember information about last flush
        self.last_sent = None
        self.previous = {}

        super(ConfigdClient, self).__init__(*args, **kwargs)

    def config(self, payload, checksum):
        self.previous = {}  # If anything changed, forget what was previously sent
        self.current = {
            'data': payload,
            'checksum': checksum,
        }

    def flush(self, resend_wait_time=None):
        now = int(time.time())

        resend_wait_time = DEFAULT_RESEND_WAIT_TIME if resend_wait_time is None else resend_wait_time

        # We know we're resending if what was previously sent was stored and it's been long enough between flushes
        resending = self.previous and self.last_sent and (now - self.last_sent > resend_wait_time)

        if not self.current and not resending:
            # Always return object definitions in case there are children and the definition is required to attached
            return {'object': self.object.definition}

        self.last_sent = now
        if not resending:  # self.current will be stored
            self.previous = copy.deepcopy(self.current)

        self.current = {}
        return {
            'object': self.object.definition,
            'config': self.previous,
            'agent': self.context.version
        }
