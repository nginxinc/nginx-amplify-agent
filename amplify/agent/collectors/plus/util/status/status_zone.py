# -*- coding: utf-8 -*-
import copy


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


def collect_http_request(collector, data, stamp):
    counted_vars = {
        'plus.http.request.count': data['requests']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_http_responses(collector, data, stamp):
    responses = data['responses']

    counted_vars = {
        'plus.http.response.count': responses['total'],
        'plus.http.status.1xx': responses['1xx'],
        'plus.http.status.2xx': responses['2xx'],
        'plus.http.status.3xx': responses['3xx'],
        'plus.http.status.4xx': responses['4xx'],
        'plus.http.status.5xx': responses['5xx']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_http_discarded(collector, data, stamp):
    counted_vars = {
        'plus.http.status.discarded': data['discarded']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


def collect_http_bytes(collector, data, stamp):
    counted_vars = {
        'plus.http.request.bytes_sent': data['sent'],
        'plus.http.request.bytes_rcvd': data['received']
    }

    collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


STATUS_ZONE_COLLECT_INDEX = [
    collect_http_request,
    collect_http_responses,
    collect_http_discarded,
    collect_http_bytes,
]
