# -*- coding: utf-8 -*-
from amplify.agent.common.context import context

from amplify.agent.objects.abstract import AbstractObject
from amplify.agent.data.eventd import INFO

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class SystemObject(AbstractObject):
    type = 'system'
    hosttype = 'hostname'

    def __init__(self, **kwargs):
        super(SystemObject, self).__init__(**kwargs)

        # have to override intervals here because new container sub objects
        self.intervals = context.app_config['containers'].get('system', {}).get('poll_intervals', {'default': 10})
        self.uuid = self.data['uuid']
        setattr(self, self.hosttype, self.data[self.hosttype])

        self._setup_meta_collector()
        self._setup_metrics_collector()

    @property
    def definition(self):
        return {'type': self.type, 'uuid': self.uuid, self.hosttype: getattr(self, self.hosttype)}

    def _setup_meta_collector(self):
        collector_cls = self._import_collector_class('system', 'meta')
        self.collectors.append(
            collector_cls(object=self, interval=self.intervals['meta'])
        )

    def _setup_metrics_collector(self):
        collector_cls = self._import_collector_class('system', 'metrics')
        self.collectors.append(
            collector_cls(object=self, interval=self.intervals['metrics'])
        )

    def start(self):
        if not context.cloud_restart and not self.running:
            # fire agent started event (if not in a container)
            if not self.in_container:
                self.eventd.event(
                    level=INFO,
                    message='agent started, version: %s, pid: %s' % (context.version, context.pid),
                    ctime=context.start_time-1  # Make sure that the start event is the first event reported.
                )
            # log agent started event
            context.log.info(
                'agent started, version=%s pid=%s uuid=%s %s=%s' %
                (context.version, context.pid, self.uuid, self.hosttype, getattr(self, self.hosttype))
            )

        super(SystemObject, self).start()

    def stop(self):
        if not context.cloud_restart:
            # fire agent stopped event (if not in a container)
            if not self.in_container:
                self.eventd.event(
                    level=INFO,
                    message='agent stopped, version: %s, pid: %s' % (context.version, context.pid)
                )

        super(SystemObject, self).stop()


class ContainerSystemObject(SystemObject):
    type = 'container'
    hosttype = 'imagename'
