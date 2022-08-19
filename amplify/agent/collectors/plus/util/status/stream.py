# -*- coding: utf-8 -*-
import copy


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


def collect_conn(collector, data, stamp):
    collector.object.statsd.gauge('plus.stream.conn.active', data['processing'], stamp=stamp)

    counted_vars = {
        'plus.stream.conn.accepted': data['connections']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_responses(collector, data, stamp):
    sessions = data['sessions']

    counted_vars = {
        'plus.stream.status.2xx': sessions['2xx'],
        'plus.stream.status.4xx': sessions['4xx'],
        'plus.stream.status.5xx': sessions['5xx']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_discarded(collector, data, stamp):
    counted_vars = {
        'plus.stream.discarded': data['discarded']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_bytes(collector, data, stamp):
    counted_vars = {
        'plus.stream.bytes_sent': data['sent'],
        'plus.stream.bytes_rcvd': data['received']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


STREAM_COLLECT_INDEX = [
    collect_conn,
    collect_responses,
    collect_discarded,
    collect_bytes,
]
