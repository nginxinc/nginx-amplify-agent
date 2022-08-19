# -*- coding: utf-8 -*-
from amplify.agent.objects.plus.object import PlusObject
from amplify.agent.collectors.plus.meta import PlusStatusObjectMetaCollector
from amplify.agent.collectors.plus.status import (
    CacheCollector,
    StatusZoneCollector,
    UpstreamCollector,
    SlabCollector,
    StreamCollector,
    StreamUpstreamCollector
)


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class PlusStatusObject(PlusObject):
    type = 'status'

    def __init__(self, *args, **kwargs):
        super(PlusStatusObject, self).__init__(**kwargs)
        self.collectors.append(
            PlusStatusObjectMetaCollector(
                object=self, interval=self.intervals['meta']
            )
        )


class NginxCacheObject(PlusStatusObject):
    type = 'cache'

    def __init__(self, *args, **kwargs):
        super(NginxCacheObject, self).__init__(**kwargs)
        self.collectors.append(
            CacheCollector(object=self, interval=self.intervals['metrics'])
        )


class NginxStatusZoneObject(PlusStatusObject):
    type = 'server_zone'
    # Needs to match the plus status JSON for collector's .gather_data()
    # method.

    def __init__(self, *args, **kwargs):
        super(NginxStatusZoneObject, self).__init__(**kwargs)
        self.collectors.append(
            StatusZoneCollector(
                object=self,
                interval=self.intervals['metrics']
            )
        )

    @property
    def definition(self):
        return {
            'type': self.type_template % 'status_zone',
            'local_id': self.local_id,
            'root_uuid': self.root_uuid
        }


class NginxUpstreamObject(PlusStatusObject):
    type = 'upstream'

    def __init__(self, *args, **kwargs):
        super(NginxUpstreamObject, self).__init__(**kwargs)
        self.collectors.append(
            UpstreamCollector(object=self, interval=self.intervals['metrics'])
        )


class NginxStreamObject(PlusStatusObject):
    type = 'stream'

    def __init__(self, *args, **kwargs):
        super(NginxStreamObject, self).__init__(**kwargs)
        self.collectors.append(
            StreamCollector(object=self, interval=self.intervals['metrics'])
        )

    @property
    def definition(self):
        return {
            'type': self.type_template % 'stream',
            'local_id': self.local_id,
            'root_uuid': self.root_uuid
        }


class NginxStreamUpstreamObject(PlusStatusObject):
    type = 'stream_upstream'

    def __init__(self, *args, **kwargs):
        super(NginxStreamUpstreamObject, self).__init__(**kwargs)
        self.collectors.append(
            StreamUpstreamCollector(
                object=self,
                interval=self.intervals['metrics']
            )
        )


class NginxSlabObject(PlusStatusObject):
    type = 'slab'

    def __init__(self, *args, **kwargs):
        super(NginxSlabObject, self).__init__(**kwargs)
        self.collectors.append(
            SlabCollector(object=self, interval=self.intervals['metrics'])
        )
