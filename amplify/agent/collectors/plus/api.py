# -*- coding: utf-8 -*-

from amplify.agent.collectors.plus.abstract import PlusAPICollector
from amplify.agent.collectors.plus.util.api.http_cache import CACHE_COLLECT_INDEX
from amplify.agent.collectors.plus.util.api.http_server_zone import STATUS_ZONE_COLLECT_INDEX
from amplify.agent.collectors.plus.util.api.http_upstream import UPSTREAM_COLLECT_INDEX, UPSTREAM_PEER_COLLECT_INDEX
from amplify.agent.collectors.plus.util.api.slab import SLAB_COLLECT_INDEX
from amplify.agent.collectors.plus.util.api.stream_server_zone import STREAM_COLLECT_INDEX
from amplify.agent.collectors.plus.util.api.stream_upstream import STREAM_UPSTREAM_COLLECT_INDEX, STREAM_UPSTREAM_PEER_COLLECT_INDEX

__author__ = "Raymond Lau"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Raymond Lau"
__email__ = "raymond.lau@nginx.com"


class ApiHttpCacheCollector(PlusAPICollector):
    short_name = 'api_cache'
    collect_index = CACHE_COLLECT_INDEX
    api_payload_path = ['http', 'caches']


class ApiHttpServerZoneCollector(PlusAPICollector):
    short_name = 'api_http_server_zone'
    collect_index = STATUS_ZONE_COLLECT_INDEX
    api_payload_path = ['http', 'server_zones']


class ApiHttpUpstreamCollector(PlusAPICollector):
    short_name = 'api_http_upstream'
    collect_index = UPSTREAM_PEER_COLLECT_INDEX
    additional_collect_index = UPSTREAM_COLLECT_INDEX
    api_payload_path = ['http', 'upstreams']

    def collect_from_data(self, data, stamp):
        """

        :param data:
        :param stamp:
        :return:
        """
        peers = data.get('peers', data) if isinstance(data, dict) else data
        for peer in peers:
            super(ApiHttpUpstreamCollector, self).collect_from_data(peer, stamp)

        for method in self.additional_collect_index:
            method(self, data, stamp)

        try:
            self.finalize_latest()
        except Exception as e:
            self.handle_exception(self.finalize_latest, e)


class ApiSlabCollector(PlusAPICollector):
    short_name = 'api_slab'
    collect_index = SLAB_COLLECT_INDEX
    api_payload_path = ['slabs']


class ApiStreamServerZoneCollector(ApiHttpServerZoneCollector):
    short_name = 'api_stream_server_zone'
    collect_index = STREAM_COLLECT_INDEX
    api_payload_path = ['stream', 'server_zones']


class ApiStreamUpstreamCollector(ApiHttpUpstreamCollector):
    short_name = 'api_stream_upstream'
    collect_index = STREAM_UPSTREAM_PEER_COLLECT_INDEX
    additional_collect_index = STREAM_UPSTREAM_COLLECT_INDEX
    api_payload_path = ['stream', 'upstreams']
