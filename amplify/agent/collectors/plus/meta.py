# -*- coding: utf-8 -*-
from amplify.agent.common.context import context
from amplify.agent.collectors.abstract import AbstractMetaCollector
from amplify.agent.objects.plus.api import TYPE_MAP


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class PlusStatusObjectMetaCollector(AbstractMetaCollector):
    short_name = 'status_meta'

    def __init__(self, **kwargs):
        super(PlusStatusObjectMetaCollector, self).__init__(**kwargs)
        self.register(
            self.version
        )

    @property
    def default_meta(self):
        zone = self.object.type if self.object.type != 'server_zone' else 'status_zone'
        meta = {
            'type': self.object.type_template % zone,
            'local_name': self.object.local_name,
            'local_id': self.object.local_id,
            'root_uuid': context.uuid,
            'hostname': context.app_config['credentials']['imagename'] or context.hostname,
            'version': None
        }
        return meta

    def version(self):
        parent = context.objects.find_parent(obj=self.object)
        self.meta['version'] = parent.version if parent else None


class PlusApiObjectMetaCollector(AbstractMetaCollector):
    short_name = 'api_meta'

    def __init__(self, **kwargs):
        super(PlusApiObjectMetaCollector, self).__init__(**kwargs)
        self.register(
            self.version
        )

    @property
    def default_meta(self):
        mapped_type = TYPE_MAP.get(self.object.type, self.object.type)
        zone = mapped_type if mapped_type != 'server_zone' else 'status_zone'
        meta = {
            'type': self.object.type_template % zone,
            'local_name': self.object.local_name,
            'local_id': self.object.local_id,
            'root_uuid': context.uuid,
            'hostname': context.app_config['credentials']['imagename'] or context.hostname,
            'version': None
        }
        return meta

    def version(self):
        parent = context.objects.find_parent(obj=self.object)
        self.meta['version'] = parent.version if parent else None

