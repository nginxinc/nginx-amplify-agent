# -*- coding: utf-8 -*-
import time

from amplify.agent.common.context import context
from amplify.agent.collectors.abstract import AbstractMetricsCollector
from amplify.ext.phpfpm.util.fpmstatus import PHPFPMStatus


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class PHPFPMPoolMetricsCollector(AbstractMetricsCollector):
    """
    Metrics collector.  Spawned per pool.  Queries status page and increments
    metrics in Pool and Master objects
    """
    short_name = 'phpfpm_pool_metrics'

    def __init__(self, **kwargs):
        super(PHPFPMPoolMetricsCollector, self).__init__(**kwargs)

        self.status_page = self._setup_status_page()
        self._current = None
        self._current_stamp = None
        self._parent = None
        # TODO: Consider a more robust way for accessing parent metrics
        #       collector

        if self.status_page is not None:
            self.register(
                self.collect_status_page
            )

    def _setup_status_page(self):
        listen = self.object.flisten

        if listen.startswith('/'):
            return PHPFPMStatus(
                path=listen, url=self.object.status_path
            )
        elif ':' in listen:
            host, port = listen.split(':')
            return PHPFPMStatus(
                host=host, port=int(port), url=self.object.status_path
            )
        elif listen.isdigit():
            port = int(listen)
            return PHPFPMStatus(
                host='127.0.0.1', port=port, url=self.object.status_path
            )

        context.log.error(
            'failed to parse listen for "%s" pool [listen:"%s", file:"%s"]' %
            (self.object.name, self.object.file, self.object.listen)
        )

    @staticmethod
    def _parse_status_page(status_page):
        result = {}
        if isinstance(status_page, str):
            for line in status_page.split('\n'):
                split_line = line.split(':', 1)
                if len(split_line) == 2:
                    key, value = map(lambda string: string.strip(), split_line)
                    result[key] = value

        return result

    def collect(self, *args, **kwargs):
        """
        Basic collect method with initial logic for storing status pages for\
        parsing.
        """
        # hit the status_page and try to store parsed results in _current
        self._current = self._parse_status_page(self.status_page.get_status())
        self._current_stamp = int(time.time())

        # load the parent object reference to minimize calls to ObjectTank
        self._parent = context.objects.find_parent(obj=self.object)

        # if self._parent is None then something is wrong...
        if self._parent is None:
            context.log.debug(
                '%s failed to collect because parent was "None"' %
                self.short_name
            )
            # TODO: Create a Naas error to serve as this condition and pass it
            #       to self.handle_exception.

            self._current = None  # clear current to save memory
            self._current_stamp = None
            return

        super(PHPFPMPoolMetricsCollector, self).collect(*args, **kwargs)

        try:
            self.increment_counters()
        except Exception as e:
            self.handle_exception(self.increment_counters, e)

        try:
            self.finalize_gauges()
        except Exception as e:
            self.handle_exception(self.finalize_gauges, e)

        self._current = None  # clear current to save memory
        self._current_stamp = None
        self._parent = None
        # clear parent reference to avoid stale refs preventing GC cleanup

    def collect_status_page(self):
        metric_map = {
            'counters': {
                'php.fpm.conn.accepted': 'accepted conn',
                'php.fpm.queue.current': 'listen queue',
                'php.fpm.slow_req': 'slow requests'
            },
            'gauges': {
                'php.fpm.queue.len': 'listen queue len',
                'php.fpm.queue.max': 'max listen queue',
                'php.fpm.proc.idle': 'idle processes',
                'php.fpm.proc.active': 'active processes',
                'php.fpm.proc.total': 'total processes',
                'php.fpm.proc.max_child': 'max children reached',
                'php.fpm.proc.max_active': 'max active processes',
            }
        }

        # counters

        counted_vars = {}
        for metric, status_name in metric_map['counters'].items():
            if status_name in self._current:
                counted_vars[metric] = int(self._current[status_name])

        self.aggregate_counters(
            counted_vars, stamp=self._current_stamp
        )
        self._parent.collectors[1].aggregate_counters(
            counted_vars, stamp=self._current_stamp
        )

        # gauges

        tracked_gauges = {}
        for metric, status_name in metric_map['gauges'].items():
            if status_name in self._current:
                tracked_gauges[metric] = {
                    self.object.definition_hash: int(self._current[status_name])
                }

        self.aggregate_gauges(
            tracked_gauges, stamp=self._current_stamp
        )
        self._parent.collectors[1].aggregate_gauges(
            tracked_gauges, stamp=self._current_stamp
        )
