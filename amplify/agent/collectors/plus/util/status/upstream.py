# -*- coding: utf-8 -*-
import copy


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


def collect_active_connections(collector, data, stamp):
    collector.object.statsd.gauge('plus.upstream.conn.active', data['active'], stamp=stamp)


def collect_upstream_request(collector, data, stamp):
    counted_vars = {
        'plus.upstream.request.count': data['requests']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_upstream_header_time(collector, data, stamp):
    if 'header_time' in data:
        time_in_seconds = float(data['header_time']) / 1000
        collector.object.statsd.timer('plus.upstream.header.time', float('%.3f' % time_in_seconds))


def collect_upstream_response_time(collector, data, stamp):
    if 'response_time' in data:
        time_in_seconds = float(data['response_time']) / 1000
        collector.object.statsd.timer('plus.upstream.response.time', float('%.3f' % time_in_seconds))


def collect_upstream_responses(collector, data, stamp):
    responses = data['responses']

    counted_vars = {
        'plus.upstream.response.count': responses['total'],
        'plus.upstream.status.1xx': responses['1xx'],
        'plus.upstream.status.2xx': responses['2xx'],
        'plus.upstream.status.3xx': responses['3xx'],
        'plus.upstream.status.4xx': responses['4xx'],
        'plus.upstream.status.5xx': responses['5xx']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_upstream_bytes(collector, data, stamp):
    counted_vars = {
        'plus.upstream.bytes_sent': data['sent'],
        'plus.upstream.bytes_rcvd': data['received']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_upstream_fails(collector, data, stamp):
    counted_vars = {
        'plus.upstream.fails.count': data['fails'],
        'plus.upstream.unavail.count': data['unavail']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_upstream_health_checks(collector, data, stamp):
    health_checks = data['health_checks']

    counted_vars = {
        'plus.upstream.health.checks': health_checks['checks'],
        'plus.upstream.health.fails': health_checks['fails'],
        'plus.upstream.health.unhealthy': health_checks['unhealthy']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_upstream_queue(collector, data, stamp):
    queue = data.get('queue')

    if queue:
        collector.object.statsd.gauge('plus.upstream.queue.size', queue['size'], stamp=stamp)

        counted_vars = {
            'plus.upstream.queue.overflows': queue['overflows'],
        }

        collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_upstream_peer_count(collector, data, stamp):
    latest_vars = [
        'plus.upstream.peer.count'
    ]

    if data['state'].lower() == 'up':
        collector.aggregate_latest(latest_vars, stamp=stamp)


def collect_upstream_conn_keepalive_zombies(collector, data, stamp):
    if 'keepalive' in data:
        collector.object.statsd.gauge('plus.upstream.conn.keepalive', data['keepalive'], stamp=stamp)

    if 'zombies' in data:
        collector.object.statsd.gauge('plus.upstream.zombies', data['zombies'], stamp=stamp)


UPSTREAM_PEER_COLLECT_INDEX = [
    collect_active_connections,
    collect_upstream_request,
    collect_upstream_header_time,
    collect_upstream_response_time,
    collect_upstream_responses,
    collect_upstream_bytes,
    collect_upstream_fails,
    collect_upstream_health_checks,
    collect_upstream_queue,
    collect_upstream_peer_count,

]

UPSTREAM_COLLECT_INDEX = [
    collect_upstream_conn_keepalive_zombies
]