# -*- coding: utf-8 -*-
import re
import time

import psutil

from gevent import GreenletExit

from amplify.agent.common.util.plus import traverse_plus_api
from amplify.agent.collectors.abstract import AbstractMetricsCollector
from amplify.agent.collectors.plus.util.api import http_cache as api_http_cache
from amplify.agent.collectors.plus.util.api import http_server_zone as api_http_server_zone
from amplify.agent.collectors.plus.util.api import http_upstream as api_http_upstream
from amplify.agent.collectors.plus.util.api import slab as api_slab
from amplify.agent.collectors.plus.util.api import stream_server_zone as api_stream_server_zone
from amplify.agent.collectors.plus.util.api import stream_upstream as api_stream_upstream
from amplify.agent.collectors.plus.util.status import cache as status_cache
from amplify.agent.collectors.plus.util.status import status_zone as status_http_server_zone
from amplify.agent.collectors.plus.util.status import upstream as status_http_upstream
from amplify.agent.collectors.plus.util.status import slab as status_slab
from amplify.agent.collectors.plus.util.status import stream as status_stream_server_zone
from amplify.agent.collectors.plus.util.status import stream_upstream as status_stream_upstream
from amplify.agent.common.context import context
from amplify.agent.common.errors import AmplifyParseException
from amplify.agent.common.util.ps import Process
from amplify.agent.data.eventd import WARNING

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"

STUB_RE = re.compile(r'^Active connections: (?P<connections>\d+)\s+[\w ]+\n'
                     r'\s+(?P<accepts>\d+)'
                     r'\s+(?P<handled>\d+)'
                     r'\s+(?P<requests>\d+)'
                     r'\s+Reading:\s+(?P<reading>\d+)'
                     r'\s+Writing:\s+(?P<writing>\d+)'
                     r'\s+Waiting:\s+(?P<waiting>\d+)')


class NginxMetricsCollector(AbstractMetricsCollector):
    short_name = 'nginx_metrics'
    status_metric_key = 'nginx.status'

    def __init__(self, **kwargs):
        super(NginxMetricsCollector, self).__init__(**kwargs)
        self.processes = [Process(pid) for pid in self.object.workers]
        self.zombies = set()

        self.register(
            self.workers_count,
            self.memory_info,
            self.workers_fds_count,
            self.workers_cpu,
            self.global_metrics,
            self.reloads_and_restarts_count,
        )
        if not self.in_container:
            self.register(
                self.workers_rlimit_nofile,
                self.workers_io
            )

    def handle_exception(self, method, exception):
        if isinstance(exception, psutil.NoSuchProcess):

            # Log exception
            context.log.warning(
                'failed to collect metrics %s due to %s, object restart needed (PID: %s)' %
                (method.__name__, exception.__class__.__name__, exception.pid)
            )
            # since the PID no longer exists, mark the object as needing restart for safety
            self.object.need_restart = True
        else:
            # Fire event warning.
            self.object.eventd.event(
                level=WARNING,
                message="can't obtain worker process metrics (maybe permissions?)",
                onetime=True
            )
            super(NginxMetricsCollector, self).handle_exception(method, exception)

    def reloads_and_restarts_count(self):
        self.object.statsd.incr('nginx.master.reloads', self.object.reloads)
        self.object.reloads = 0

    def workers_count(self):
        """nginx.workers.count"""
        self.object.statsd.gauge('nginx.workers.count', len(self.object.workers))

    def handle_zombie(self, pid):
        """
        removes pid from workers list
        :param pid: zombie pid
        """
        context.log.warning('zombie process %s found' % pid)
        self.zombies.add(pid)

    def memory_info(self):
        """
        memory info

        nginx.workers.mem.rss
        nginx.workers.mem.vms
        nginx.workers.mem.rss_pct
        """
        rss, vms, pct = 0, 0, 0.0
        for p in self.processes:
            if p.pid in self.zombies:
                continue
            try:
                mem_info = p.memory_info()
                rss += mem_info.rss
                vms += mem_info.vms
                pct += p.memory_percent()
            except psutil.ZombieProcess:
                self.handle_zombie(p.pid)

        self.object.statsd.gauge('nginx.workers.mem.rss', rss)
        self.object.statsd.gauge('nginx.workers.mem.vms', vms)
        self.object.statsd.gauge('nginx.workers.mem.rss_pct', pct)

    def workers_fds_count(self):
        """nginx.workers.fds_count"""
        fds = 0
        for p in self.processes:
            if p.pid in self.zombies:
                continue
            try:
                fds += p.num_fds()
            except psutil.ZombieProcess:
                self.handle_zombie(p.pid)
        self.object.statsd.incr('nginx.workers.fds_count', fds)

    def workers_cpu(self):
        """
        cpu

        nginx.workers.cpu.system
        nginx.workers.cpu.user
        """
        worker_user, worker_sys = 0.0, 0.0
        for p in self.processes:
            if p.pid in self.zombies:
                continue
            try:
                u, s = p.cpu_percent()
                worker_user += u
                worker_sys += s
            except psutil.ZombieProcess:
                self.handle_zombie(p.pid)
        self.object.statsd.gauge('nginx.workers.cpu.total', worker_user + worker_sys)
        self.object.statsd.gauge('nginx.workers.cpu.user', worker_user)
        self.object.statsd.gauge('nginx.workers.cpu.system', worker_sys)

    def global_metrics(self):
        """
        check if found api or extended status, collect "global" metrics from it
        don't look for stub_status
        if there's no extended status or N+ API easily accessible, proceed with stub_status
        """
        if self.object.api_enabled and self.object.api_internal_url:
            self.plus_api()
        elif self.object.plus_status_enabled and self.object.plus_status_internal_url \
            and self.object.status_directive_supported:
            self.plus_status()
        elif self.object.stub_status_enabled and self.object.stub_status_url:
            self.stub_status()
        else:
            return

    def stub_status(self):
        """
        stub status metrics

        nginx.http.conn.current = ss.active
        nginx.http.conn.active = ss.active - ss.waiting
        nginx.http.conn.idle = ss.waiting
        nginx.http.request.count = ss.requests ## counter
        nginx.http.request.reading = ss.reading
        nginx.http.request.writing = ss.writing
        nginx.http.conn.dropped = ss.accepts - ss.handled ## counter
        nginx.http.conn.accepted = ss.accepts ## counter
        """
        stub_body = ''
        stub = {}
        stub_time = int(time.time())

        # get stub status body
        try:
            stub_body = context.http_client.get(self.object.stub_status_url, timeout=1, json=False, log=False)
        except GreenletExit:
            # we caught an exit signal in the middle of processing so raise it.
            raise
        except:
            context.log.error('failed to check stub_status url %s' % self.object.stub_status_url)
            context.log.debug('additional info', exc_info=True)
            stub_body = None

        if not stub_body:
            return

        # parse body
        try:
            gre = STUB_RE.match(stub_body)
            if not gre:
                raise AmplifyParseException(message='stub status %s' % stub_body)
            for field in ('connections', 'accepts', 'handled', 'requests', 'reading', 'writing', 'waiting'):
                stub[field] = int(gre.group(field))
        except:
            context.log.error('failed to parse stub_status body')
            raise

        # store some variables for further use
        stub['dropped'] = stub['accepts'] - stub['handled']

        # gauges
        self.object.statsd.gauge('nginx.http.conn.current', stub['connections'])
        self.object.statsd.gauge('nginx.http.conn.active', stub['connections'] - stub['waiting'])
        self.object.statsd.gauge('nginx.http.conn.idle', stub['waiting'])
        self.object.statsd.gauge('nginx.http.request.writing', stub['writing'])
        self.object.statsd.gauge('nginx.http.request.reading', stub['reading'])
        self.object.statsd.gauge('nginx.http.request.current', stub['reading'] + stub['writing'])

        # counters
        counted_vars = {
            'nginx.http.request.count': 'requests',
            'nginx.http.conn.accepted': 'accepts',
            'nginx.http.conn.dropped': 'dropped'
        }
        for metric_name, stub_name in counted_vars.items():
            stamp, value = stub_time, stub[stub_name]
            prev_stamp, prev_value = self.previous_counters.get(metric_name, (None, None))

            if isinstance(prev_value, (int, float, complex)) and prev_stamp and prev_stamp != stamp:
                value_delta = value - prev_value
                self.object.statsd.incr(metric_name, value_delta)

            self.previous_counters[metric_name] = [stamp, value]

    def plus_status(self):
        """
        plus status metrics

        nginx.http.conn.accepted = connections.accepted  ## counter
        nginx.http.conn.dropped = connections.dropped  ## counter
        nginx.http.conn.active = connections.active
        nginx.http.conn.current = connections.active + connections.idle
        nginx.http.conn.idle = connections.idle
        nginx.http.request.count = requests.total  ## counter
        nginx.http.request.current = requests.current

        plus.http.ssl.handshakes = ssl.handshakes
        plus.http.ssl.failed = ssl.handshakes_failed
        plus.http.ssl.reuses = ssl.session_reuses

        also here we run plus metrics collection
        """
        stamp = int(time.time())

        # get plus status body
        try:
            status = context.http_client.get(self.object.plus_status_internal_url, timeout=1, log=False)

            # modify status to move stream data up a level
            if 'stream' in status:
                status['streams'] = status['stream'].get('server_zones', {})
                status['stream_upstreams'] = status['stream'].get('upstreams', {})

            # Add the status payload to plus_cache so it can be parsed by other collectors (plus objects)
            context.plus_cache.put(self.object.plus_status_internal_url, (status, stamp))
        except GreenletExit:
            raise
        except:
            context.log.error('failed to check plus_status url %s' % self.object.plus_status_internal_url)
            context.log.debug('additional info', exc_info=True)
            status = None

        if not status:
            return

        connections = status.get('connections', {})
        requests = status.get('requests', {})
        ssl = status.get('ssl', {})

        # gauges
        self.object.statsd.gauge('nginx.http.conn.active', connections.get('active'))
        self.object.statsd.gauge('nginx.http.conn.idle', connections.get('idle'))
        self.object.statsd.gauge('nginx.http.conn.current', connections.get('active') + connections.get('idle'))
        self.object.statsd.gauge('nginx.http.request.current', requests.get('current'))

        # counters
        counted_vars = {
            'nginx.http.request.count': requests.get('total'),
            'nginx.http.conn.accepted': connections.get('accepted'),
            'nginx.http.conn.dropped': connections.get('dropped'),
            'plus.http.ssl.handshakes': ssl.get('handshakes'),
            'plus.http.ssl.failed': ssl.get('handshakes_failed'),
            'plus.http.ssl.reuses': ssl.get('session_reuses')
        }
        self.aggregate_counters(counted_vars, stamp=stamp)

        # aggregate plus metrics
        # caches
        caches = status.get('caches', {})
        for cache in caches.values():
            for method in status_cache.CACHE_COLLECT_INDEX:
                method(self, cache, stamp)

        # status zones
        zones = status.get('server_zones', {})
        for zone in zones.values():
            for method in status_http_server_zone.STATUS_ZONE_COLLECT_INDEX:
                method(self, zone, stamp)

        # upstreams
        upstreams = status.get('upstreams', {})
        for upstream in upstreams.values():
            # workaround for supporting old N+ format
            # http://nginx.org/en/docs/http/ngx_http_status_module.html#compatibility
            peers = upstream['peers'] if 'peers' in upstream else upstream
            for peer in peers:
                for method in status_http_upstream.UPSTREAM_PEER_COLLECT_INDEX:
                    method(self, peer, stamp)
            for method in status_http_upstream.UPSTREAM_COLLECT_INDEX:
                method(self, upstream, stamp)

        # slabs
        slabs = status.get('slabs', {})
        for slab in slabs.values():
            for method in status_slab.SLAB_COLLECT_INDEX:
                method(self, slab, stamp)

        # streams - server_zones of stream
        streams = status.get('streams', {})
        for stream in streams.values():
            for method in status_stream_server_zone.STREAM_COLLECT_INDEX:
                method(self, stream, stamp)

        # stream upstreams - upstreams of stream
        stream_upstreams = status.get('stream_upstreams', {})
        for stream_upstream in stream_upstreams.values():
            peers = stream_upstream['peers'] if 'peers' in stream_upstream else stream_upstream
            for peer in peers:
                for method in status_stream_upstream.STREAM_UPSTREAM_PEER_COLLECT_INDEX:
                    method(self, peer, stamp)
            for method in status_stream_upstream.STREAM_UPSTREAM_COLLECT_INDEX:
                method(self, stream_upstream, stamp)

        self.increment_counters()
        self.finalize_latest()

    def plus_api(self):
        """
        plus api top-level metrics

        nginx.http.conn.accepted = connections.accepted  ## counter
        nginx.http.conn.dropped = connections.dropped  ## counter
        nginx.http.conn.active = connections.active
        nginx.http.conn.current = connections.active + connections.idle
        nginx.http.conn.idle = connections.idle
        nginx.http.request.count = requests.total  ## counter
        nginx.http.request.current = requests.current

        plus.http.ssl.handshakes = ssl.handshakes
        plus.http.ssl.failed = ssl.handshakes_failed
        plus.http.ssl.reuses = ssl.session_reuses
        plus.proc.respawned = processes.respawned

        also here we run plus metrics collection
        """
        stamp = int(time.time())

        try:
            aggregated_api_payload = traverse_plus_api(
                location_prefix=self.object.api_internal_url,
                root_endpoints_to_skip=self.object.api_endpoints_to_skip
            )
        except GreenletExit:
            raise
        except:
            context.log.error('failed to check plus_api url %s' % self.object.api_internal_url)
            context.log.debug('additional info', exc_info=True)
            aggregated_api_payload = None

        if not aggregated_api_payload:
            return

        context.plus_cache.put(self.object.api_internal_url, (aggregated_api_payload, stamp))

        connections = aggregated_api_payload.get('connections', {})
        http = aggregated_api_payload.get('http', {})
        requests = http.get('requests', {})
        ssl = aggregated_api_payload.get('ssl', {})
        processes = aggregated_api_payload.get('processes', {})
        stream = aggregated_api_payload.get('stream', {})

        # gauges
        self.object.statsd.gauge('nginx.http.conn.active', connections.get('active'))
        self.object.statsd.gauge('nginx.http.conn.idle', connections.get('idle'))
        self.object.statsd.gauge('nginx.http.conn.current', connections.get('active') + connections.get('idle'))
        self.object.statsd.gauge('nginx.http.request.current', requests.get('current'))

        # counters
        counted_vars = {
            'nginx.http.request.count': requests.get('total'),
            'nginx.http.conn.accepted': connections.get('accepted'),
            'nginx.http.conn.dropped': connections.get('dropped'),
            'plus.http.ssl.handshakes': ssl.get('handshakes'),
            'plus.http.ssl.failed': ssl.get('handshakes_failed'),
            'plus.http.ssl.reuses': ssl.get('session_reuses'),
            'plus.proc.respawned' : processes.get('respawned')
        }
        self.aggregate_counters(counted_vars, stamp=stamp)

        caches = http.get('caches', {})
        for cache in caches.values():
            for method in api_http_cache.CACHE_COLLECT_INDEX:
                method(self, cache, stamp)

        http_server_zones = http.get('server_zones', {})
        for server_zone in http_server_zones.values():
            for method in api_http_server_zone.STATUS_ZONE_COLLECT_INDEX:
                method(self, server_zone, stamp)

        http_upstreams = http.get('upstreams', {})
        for upstream in http_upstreams.values():
            for peer in upstream.get('peers', []):
                for method in api_http_upstream.UPSTREAM_PEER_COLLECT_INDEX:
                    method(self, peer, stamp)
            for method in api_http_upstream.UPSTREAM_COLLECT_INDEX:
                method(self, upstream, stamp)

        slabs = aggregated_api_payload.get('slabs', {})
        for slab in slabs.values():
            for method in api_slab.SLAB_COLLECT_INDEX:
                method(self, slab, stamp)

        stream_server_zones = stream.get('server_zones', {})
        for server_zone in stream_server_zones.values():
            for method in api_stream_server_zone.STREAM_COLLECT_INDEX:
                method(self, server_zone, stamp)

        stream_upstreams = stream.get('upstreams', {})
        for upstream in stream_upstreams.values():
            for peer in upstream.get('peers', []):
                for method in api_stream_upstream.STREAM_UPSTREAM_PEER_COLLECT_INDEX:
                    method(self, peer, stamp)
            for method in api_stream_upstream.STREAM_UPSTREAM_COLLECT_INDEX:
                method(self, upstream, stamp)

        self.increment_counters()
        self.finalize_latest()

    def workers_rlimit_nofile(self):
        """
        nginx.workers.rlimit_nofile

        sum for all hard limits (second value of rlimit)
        """
        rlimit = 0
        for p in self.processes:
            if p.pid in self.zombies:
                continue
            try:
                rlimit += p.rlimit_nofile()
            except psutil.ZombieProcess:
                self.handle_zombie(p.pid)
        self.object.statsd.gauge('nginx.workers.rlimit_nofile', rlimit)

    def workers_io(self):
        """
        io

        nginx.workers.io.kbs_r
        nginx.workers.io.kbs_w
        """
        # collect raw data
        read, write = 0, 0
        for p in self.processes:
            if p.pid in self.zombies:
                continue
            try:
                io = p.io_counters()
                read += io.read_bytes
                write += io.write_bytes
            except psutil.ZombieProcess:
                self.handle_zombie(p.pid)
        current_stamp = int(time.time())

        # kilobytes!
        read /= 1024
        write /= 1024

        # get deltas and store metrics
        for metric_name, value in {'nginx.workers.io.kbs_r': read, 'nginx.workers.io.kbs_w': write}.items():
            prev_stamp, prev_value = self.previous_counters.get(metric_name, (None, None))
            if isinstance(prev_value, (int, float, complex)) and prev_stamp and prev_stamp != current_stamp:
                value_delta = value - prev_value
                self.object.statsd.incr(metric_name, value_delta)
            self.previous_counters[metric_name] = (current_stamp, value)


class GenericLinuxNginxMetricsCollector(NginxMetricsCollector):
    pass


class DebianNginxMetricsCollector(NginxMetricsCollector):
    pass


class CentosNginxMetricsCollector(NginxMetricsCollector):
    pass


class GentooNginxMetricsCollector(NginxMetricsCollector):
    pass


class FreebsdNginxMetricsCollector(NginxMetricsCollector):

    def workers_fds_count(self):
        """
        This doesn't work on FreeBSD
        """
        pass
