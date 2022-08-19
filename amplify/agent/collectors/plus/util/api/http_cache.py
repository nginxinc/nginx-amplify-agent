# -*- coding: utf-8 -*-
import copy


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


def collect_cache_size(collector, data, stamp):
    collector.object.statsd.gauge('plus.cache.size', data['size'], stamp=stamp)
    if 'max_size' in data:
        collector.object.statsd.gauge('plus.cache.max_size', data['max_size'], stamp=stamp)


def collect_cache_metrics(collector, data, stamp):
    types = [
        'bypass',
        'expired',
        'hit',
        'miss',
        'revalidated',
        'stale',
        'updating'
    ]

    for label in types:
        data_bucket = data[label]

        metric_base = 'plus.cache.%s' % label

        filtered_names = filter(
            lambda name: name not in ('responses_written', 'bytes_written'),
            data_bucket.keys()
        )
        counted_vars = {}
        for name in filtered_names:
            metric_name = metric_base + '.%s' % name
            counted_vars[metric_name] = data_bucket[name]

        # metric base is used to store total responses
        counted_vars.update({
            metric_base: data_bucket['responses']
        })

        collector.aggregate_counters(copy.deepcopy(counted_vars), stamp=stamp)


CACHE_COLLECT_INDEX = [
    collect_cache_size,
    collect_cache_metrics,
]
