# -*- coding: utf-8 -*-
import copy


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


def collect_active_connections(collector, data, stamp):
    collector.object.statsd.gauge('plus.stream.upstream.conn.active', data['active'], stamp=stamp)


def collect_total_connections(collector, data, stamp):
    counted_vars = {
        'plus.stream.upstream.conn.count': data['connections']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_timers(collector, data, stamp):
    if 'connect_time' in data:
        time_in_seconds = float(data['connect_time']) / 1000
        collector.object.statsd.timer('plus.stream.upstream.conn.time', float('%.3f' % time_in_seconds))

    if 'first_byte_time' in data:
        time_in_seconds = float(data['first_byte_time']) / 1000
        collector.object.statsd.timer('plus.stream.upstream.conn.ttfb', float('%.3f' % time_in_seconds))

    if 'response_time' in data:
        time_in_seconds = float(data['response_time']) / 1000
        collector.object.statsd.timer('plus.stream.upstream.response.time', float('%.3f' % time_in_seconds))


def collect_bytes(collector, data, stamp):
    counted_vars = {
        'plus.stream.upstream.bytes_sent': data['sent'],
        'plus.stream.upstream.bytes_rcvd': data['received']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_fails_unavail(collector, data, stamp):
    counted_vars = {
        'plus.stream.upstream.fails.count': data['fails'],
        'plus.stream.upstream.unavail.count': data['unavail']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_health_checks(collector, data, stamp):
    health_checks = data['health_checks']

    counted_vars = {
        'plus.stream.upstream.health.checks': health_checks['checks'],
        'plus.stream.upstream.health.fails': health_checks['fails'],
        'plus.stream.upstream.health.unhealthy': health_checks['unhealthy']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_peer_count(collector, data, stamp):
    latest_vars = [
        'plus.stream.upstream.peer.count'
    ]

    if data['state'].lower() == 'up':
        collector.aggregate_latest(latest_vars, stamp=stamp)


def collect_zombies(collector, data, stamp):
    if 'zombies' in data:
        collector.object.statsd.gauge('plus.stream.upstream.zombies', data['zombies'], stamp=stamp)


STREAM_UPSTREAM_PEER_COLLECT_INDEX = [
    collect_active_connections,
    collect_total_connections,
    collect_timers,
    collect_bytes,
    collect_fails_unavail,
    collect_health_checks,
    collect_peer_count
]

STREAM_UPSTREAM_COLLECT_INDEX = [
    collect_zombies
]