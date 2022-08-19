# -*- coding: utf-8 -*-
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


SLAB_COLLECT_INDEX = [
    collect_pages
]
