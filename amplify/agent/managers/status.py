# -*- coding: utf-8 -*-
from amplify.agent.common.context import context
from amplify.agent.managers.abstract import ObjectManager
from amplify.agent.objects.plus.status import (
    NginxCacheObject,
    NginxStatusZoneObject,
    NginxUpstreamObject,
    NginxSlabObject,
    NginxStreamObject,
    NginxStreamUpstreamObject
)
import time


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class StatusManager(ObjectManager):
    """
    Manager for Plus objects (Cache, StatusZone, Upstream, Slab).
    Traverses all Nginx objects and looks for Plus instances.
    After identifying Nginx-Plus instances, it queries the plus_cache for the
    object in order to manage the child Plus objects much like NginxManager
    does for Nginx objects.

    Spawns old status objects.
    """
    name = 'status_manager'
    type = 'status'
    types = (
        'cache',
        'server_zone',
        'upstream',
        'slab',
        'stream',
        'stream_upstream'
    )

    def _status_objects(self):
        return filter(
            lambda obj: not context.objects.find_parent(obj=obj).api_enabled,
            context.objects.find_all(types=self.types)
        )

    def _discover(self):
        if time.time() > self.last_discover + (self.config_intervals.get('discover') or self.interval):
            self._discover_objects()
        context.log.debug('%s objects: %s' % (
            self.type,
            [obj.definition_hash for obj in self._status_objects()]
        ))

    def _discover_objects(self):
        # Find nginx+ with status enabled and not api enabled
        status_nginxs = filter(
            lambda x: x.plus_status_enabled and not x.api_enabled,
            context.objects.find_all(types=('nginx',))
        )

        # filter status objects by checking type and making sure api is not
        # enabled in parent nginx
        existing_hashes = map(lambda x: x.local_id, self._status_objects())

        discovered_hashes = []

        for nginx in status_nginxs:
            plus_payload, stamp = context.plus_cache.get_last(nginx.plus_status_internal_url)

            # skip nginx+'s that haven't collected their first plus payload
            if not plus_payload or not stamp:
                continue

            status_object_map = {
                'caches': NginxCacheObject,
                'server_zones': NginxStatusZoneObject,
                'upstreams': NginxUpstreamObject,
                'slabs': NginxSlabObject,
                'streams': NginxStreamObject,
                'stream_upstreams': NginxStreamUpstreamObject
            }

            # for each instance of each kind of object
            for key, cls in status_object_map.items():
                for name in plus_payload.get(key, []):
                    # discover the object
                    obj_hash = cls.hash_local(nginx.local_id, cls.type, name)
                    discovered_hashes.append(obj_hash)

                    # new objects get created and registered
                    if obj_hash not in existing_hashes:
                        new_obj = cls(parent_local_id=nginx.local_id, local_name=name)
                        self.objects.register(new_obj, parent_id=nginx.id)

        dropped_hashes = filter(lambda x: x not in discovered_hashes, existing_hashes)
        for obj in self._status_objects():
            if obj.local_id in dropped_hashes:
                obj.stop()
                self.objects.unregister(obj)

    def _start_objects(self):
        for managed_obj in self._status_objects():
            managed_obj.start()
            for child_obj in self.objects.find_all(obj_id=managed_obj.id, children=True, include_self=False):
                child_obj.start()

    def _stop_objects(self):
        for managed_obj in self._status_objects():
            for child_obj in self.objects.find_all(obj_id=managed_obj.id, children=True, include_self=False):
                child_obj.stop()
                self.objects.unregister(obj=child_obj)
            managed_obj.stop()
            self.objects.unregister(obj=managed_obj)
