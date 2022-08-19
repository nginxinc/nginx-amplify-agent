# -*- coding: utf-8 -*-
from amplify.agent.objects.plus.object import PlusObject
from amplify.agent.collectors.plus.api import (
    ApiHttpCacheCollector,
    ApiHttpServerZoneCollector,
    ApiHttpUpstreamCollector,
    ApiSlabCollector,
    ApiStreamServerZoneCollector,
    ApiStreamUpstreamCollector
)


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


# internal object type : definition type
TYPE_MAP = {
    'http_cache': 'cache',
    'http_server_zone': 'status_zone',
    'http_upstream': 'upstream',
    'slab': 'slab',
    'stream_server_zone': 'stream',
    'stream_upstream': 'stream_upstream',
}


class PlusApiObject(PlusObject):
    type = 'api'

    def __init__(self, *args, **kwargs):
        super(PlusApiObject, self).__init__(**kwargs)

        from amplify.agent.collectors.plus.meta import PlusApiObjectMetaCollector

        self.collectors.append(
            PlusApiObjectMetaCollector(
                object=self, interval=self.intervals['meta']
            )
        )

    @property
    def definition(self):
        return {
            'type': self.type_template % TYPE_MAP.get(self.type, self.type),
            'local_id': self.local_id,
            'root_uuid': self.root_uuid
        }

    @property
    def local_id_args(self):
        # override the local_id_args to convert type for hashing purposes
        return (
            self.parent_local_id,
            TYPE_MAP.get(self.type, self.type),
            self.local_name
        )


class NginxApiHttpCacheObject(PlusApiObject):
    type = 'http_cache'

    def __init__(self, *args, **kwargs):
        super(NginxApiHttpCacheObject, self).__init__(**kwargs)
        self.collectors.append(
            ApiHttpCacheCollector(
                object=self,
                interval=self.intervals['metrics']
            )
        )


class NginxApiHttpServerZoneObject(PlusApiObject):
    type = 'http_server_zone'

    def __init__(self, *args, **kwargs):
        super(NginxApiHttpServerZoneObject, self).__init__(**kwargs)
        self.collectors.append(
            ApiHttpServerZoneCollector(
                object=self,
                interval=self.intervals['metrics']
            )
        )


class NginxApiHttpUpstreamObject(PlusApiObject):
    type = 'http_upstream'

    def __init__(self, *args, **kwargs):
        super(NginxApiHttpUpstreamObject, self).__init__(**kwargs)
        self.collectors.append(
            ApiHttpUpstreamCollector(
                object=self,
                interval=self.intervals['metrics']
            )
        )


class NginxApiStreamServerZoneObject(PlusApiObject):
    type = 'stream_server_zone'

    def __init__(self, *args, **kwargs):
        super(NginxApiStreamServerZoneObject, self).__init__(**kwargs)
        self.collectors.append(
            ApiStreamServerZoneCollector(
                object=self, interval=self.intervals['metrics']
            )
        )


class NginxApiStreamUpstreamObject(PlusApiObject):
    type = 'stream_upstream'

    def __init__(self, *args, **kwargs):
        super(NginxApiStreamUpstreamObject, self).__init__(**kwargs)
        self.collectors.append(
            ApiStreamUpstreamCollector(
                object=self,
                interval=self.intervals['metrics']
            )
        )


class NginxApiSlabObject(PlusApiObject):
    type = 'slab'

    def __init__(self, *args, **kwargs):
        super(NginxApiSlabObject, self).__init__(**kwargs)
        self.collectors.append(
            ApiSlabCollector(
                object=self,
                interval=self.intervals['metrics']
            )
        )
