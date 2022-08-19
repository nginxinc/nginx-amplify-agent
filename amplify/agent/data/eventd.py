# -*- coding: utf-8 -*-
import copy
import hashlib
import time

from amplify.agent.data.abstract import CommonDataClient


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


DEBUG = 0
INFO = 1
WARNING = 2
ERROR = 3
CRITICAL = 4


class Event(object):
    """
    Event representation
    """
    def __init__(self, level, message):
        self.level = level
        self.message = message
        self.stamp = int(time.time())
        self.category = 'agent'
        self.string_id = '%s_%s' % (self.message, self.level)
        self.id = hashlib.sha256(self.string_id.encode('utf-8')).hexdigest()
        self.counter = 1

    def inc(self):
        self.counter += 1

    def dict(self):
        return {
            'level': self.level,
            'message': self.message,
            'ctime': self.stamp,
            'category': self.category,
            'counter': self.counter
        }


class EventdClient(CommonDataClient):

    def __init__(self, *args, **kwargs):
        # Import context as a class object to avoid circular import on statsd.  This could be refactored later.
        from amplify.agent.common.context import context
        self.context = context

        super(EventdClient, self).__init__(*args, **kwargs)
        self.onetimers = {}

    def event(self, level=DEBUG, message=None, onetime=False, ctime=None):
        event = Event(level, message)

        if ctime:  # Override the event timestamp.
            event.stamp = ctime

        if onetime and event.id in self.onetimers:
            return
        else:
            self.onetimers[event.id] = True

        if event.id in self.current:
            stored_event = self.current[event.id]
            stored_event.inc()
        else:
            self.current[event.id] = event

    def flush(self):
        """
        Compresses equal events to one record with count

        :return: dict of payload
        """
        if not self.current:
            return {'object': self.object.definition}

        delivery = copy.deepcopy(self.current)
        self.current = {}

        return {
            'object': self.object.definition,
            'events': [event.dict() for event in delivery.values()]
        }
