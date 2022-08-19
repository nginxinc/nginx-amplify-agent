# -*- coding: utf-8 -*-
from amplify.agent.common.context import context
from amplify.agent.managers.abstract import ObjectManager
from amplify.agent.objects.plus.api import (
    TYPE_MAP,
    NginxApiHttpCacheObject,
    NginxApiHttpServerZoneObject,
    NginxApiHttpUpstreamObject,
    NginxApiSlabObject,
    NginxApiStreamServerZoneObject,
    NginxApiStreamUpstreamObject
)
import time


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class ApiManager(ObjectManager):
    """
    Manager for NGINX+ object sourced from the `api` directive.  Traverses all
    nginx objects and looks for plus instances with `api_enabled`.  For these
    objects it will attempt to find a payload in the plus_cache and spawn
    objects based on the contents of the payload.

    Spawns new api objects.
    """
    name = 'api_manager'
    type = 'api'
    types = (
        'http_cache',
        'http_server_zone',
        'http_upstream',
        'stream_server_zone',
        'stream_upstream',
        'slab'
    )

    def _api_objects(self):
        return filter(
            lambda obj: context.objects.find_parent(obj=obj).api_enabled,
            context.objects.find_all(types=self.types)
        )

    def _discover(self):
        if time.time() > self.last_discover + (self.config_intervals.get('discover') or self.interval):
            self._discover_objects()
        context.log.debug('%s objects: %s' % (
            self.type,
            [obj.definition_hash for obj in self._api_objects()]
        ))

    def _discover_objects(self):
        # find nginx+ with api enabled
        api_nginxs = filter(
            lambda x: x.api_enabled,
            context.objects.find_all(types=('nginx',))
        )

        # filter api objects by checking type and making sure api is enabled in
        # parent nginx
        existing_hashes = map(lambda x: x.local_id, self._api_objects())

        discovered_hashes = []

        for nginx in api_nginxs:
            plus_payload, stamp = context.plus_cache.get_last(
                nginx.api_internal_url
            )

            # skip nginx+'s that haven't collected their first plus payload
            if not plus_payload or not stamp:
                continue

            # payload location/path : object
            api_object_map = {
                ('http', 'caches'): NginxApiHttpCacheObject,
                ('http', 'server_zones'): NginxApiHttpServerZoneObject,
                ('http', 'upstreams'): NginxApiHttpUpstreamObject,
                ('slabs',): NginxApiSlabObject,
                ('stream', 'server_zones'): NginxApiStreamServerZoneObject,
                ('stream', 'upstreams'): NginxApiStreamUpstreamObject
            }

            for path, cls in api_object_map.items():
                area = plus_payload

                for key in path:
                    area = area.get(key, {})

                for name in area.keys():
                    # discover the object
                    obj_hash = cls.hash_local(
                        nginx.local_id,
                        TYPE_MAP.get(cls.type, cls.type),
                        name
                    )
                    discovered_hashes.append(obj_hash)

                    # new objects get created and registered
                    if obj_hash not in existing_hashes:
                        new_obj = cls(
                            parent_local_id=nginx.local_id,
                            local_name=name
                        )
                        self.objects.register(new_obj, parent_id=nginx.id)

        dropped_hashes = filter(
            lambda x: x not in discovered_hashes,
            existing_hashes
        )
        for obj in self._api_objects():
            if obj.local_id in dropped_hashes:
                obj.stop()
                self.objects.unregister(obj)

    def _start_objects(self):
        for managed_obj in self._api_objects():
            managed_obj.start()
            for child_obj in self.objects.find_all(obj_id=managed_obj.id, children=True, include_self=False):
                child_obj.start()

    def _stop_objects(self):
        for managed_obj in self._api_objects():
            for child_obj in self.objects.find_all(obj_id=managed_obj.id, children=True, include_self=False):
                child_obj.stop()
                self.objects.unregister(obj=child_obj)
            managed_obj.stop()
            self.objects.unregister(obj=managed_obj)
