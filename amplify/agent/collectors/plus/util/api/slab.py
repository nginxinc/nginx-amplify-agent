# -*- coding: utf-8 -*-
import copy


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


def collect_pages(collector, data, stamp):
    pages = data['pages']
    used, free = pages['used'], pages['free']
    total = used + free
    pct_used = int(round(float(free)/float(total) * 100))

    collector.object.statsd.gauge('plus.slab.pages.used', used, stamp=stamp)
    collector.object.statsd.gauge('plus.slab.pages.free', free, stamp=stamp)
    collector.object.statsd.gauge('plus.slab.pages.total', total, stamp=stamp)
    collector.object.statsd.gauge('plus.slab.pages.pct_used', pct_used, stamp=stamp)


def collect_slots(collector, data, stamp):
    used, free = data['pages']['used'], data['pages']['free']
    total = used + free
    pct_used = int(round(float(free) / float(total) * 100))

    collector.object.statsd.gauge(
        'plus.slab' + '.used', used, stamp=stamp
    )
    collector.object.statsd.gauge(
        'plus.slab' + '.free', free, stamp=stamp
    )
    collector.object.statsd.gauge(
        'plus.slab' + '.total', total, stamp=stamp
    )
    collector.object.statsd.gauge(
        'plus.slab' + '.pct_used', pct_used, stamp=stamp
    )

    for slot, slot_data in data['slots'].items():
        # pre-format metric name
        slot_base = 'plus.slab.%s' % slot

        counted_vars = {
            slot_base + '.requests': slot_data['reqs'],
            slot_base + '.fails': slot_data['reqs']
        }
        collector.aggregate_counters(
            copy.deepcopy(counted_vars), stamp=stamp
        )


SLAB_COLLECT_INDEX = [
    collect_pages,
    collect_slots
]
