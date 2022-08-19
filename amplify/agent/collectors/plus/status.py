# -*- coding: utf-8 -*-

from amplify.agent.collectors.plus.abstract import PlusStatusCollector
from amplify.agent.collectors.plus.util.status.cache import CACHE_COLLECT_INDEX
from amplify.agent.collectors.plus.util.status.slab import SLAB_COLLECT_INDEX
from amplify.agent.collectors.plus.util.status.status_zone import (
    STATUS_ZONE_COLLECT_INDEX
)
from amplify.agent.collectors.plus.util.status.stream import (
    STREAM_COLLECT_INDEX
)
from amplify.agent.collectors.plus.util.status.stream_upstream import (
    STREAM_UPSTREAM_PEER_COLLECT_INDEX,
    STREAM_UPSTREAM_COLLECT_INDEX
)
from amplify.agent.collectors.plus.util.status.upstream import (
    UPSTREAM_PEER_COLLECT_INDEX,
    UPSTREAM_COLLECT_INDEX
)

__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class CacheCollector(PlusStatusCollector):
    short_name = 'plus_cache'
    collect_index = CACHE_COLLECT_INDEX


class StatusZoneCollector(PlusStatusCollector):
    short_name = 'plus_status_zone'
    collect_index = STATUS_ZONE_COLLECT_INDEX


class UpstreamCollector(PlusStatusCollector):
    short_name = 'plus_upstream'
    collect_index = UPSTREAM_PEER_COLLECT_INDEX
    additional_collect_index = UPSTREAM_COLLECT_INDEX

    def collect_from_data(self, data, stamp):
        """
        Aggregates all peer metrics as a single "upstream" entity.
        """
        # data.get('peers', data) is a workaround for supporting an old N+ format
        # http://nginx.org/en/docs/http/ngx_http_status_module.html#compatibility
        peers = data.get('peers', data) if isinstance(data, dict) else data
        for peer in peers:
            super(UpstreamCollector, self).collect_from_data(peer, stamp)

        for method in self.additional_collect_index:
            method(self, data, stamp)

        try:
            self.finalize_latest()
        except Exception as e:
            self.handle_exception(self.finalize_latest, e)


class SlabCollector(PlusStatusCollector):
    short_name = 'plus_slab'
    collect_index = SLAB_COLLECT_INDEX


class StreamCollector(StatusZoneCollector):
    short_name = 'plus_stream'
    collect_index = STREAM_COLLECT_INDEX


class StreamUpstreamCollector(UpstreamCollector):
    short_name = 'plus_stream_upstream'
    collect_index = STREAM_UPSTREAM_PEER_COLLECT_INDEX
    additional_collect_index = STREAM_UPSTREAM_COLLECT_INDEX
