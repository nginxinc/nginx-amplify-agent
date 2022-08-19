# -*- coding: utf-8 -*-
from amplify.agent.common.context import context
from amplify.agent.objects.abstract import AbstractObject


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class PlusObject(AbstractObject):
    """
    Common Plus object.  Supervisor for collectors and data client bucket.
    """
    type_template = 'nginx_%s'
    type = 'plus'

    def __init__(self, **kwargs):
        super(PlusObject, self).__init__(**kwargs)

        # Reset intervals to standardize intervals for all Plus objects
        self.intervals = context.app_config['containers']['plus']['poll_intervals']

        self.root_uuid = context.uuid
        self.parent_local_id = self.data['parent_local_id']
        self.local_name = self.data['local_name']
        self.name = self.local_name
        self.plus_status_internal_url_cache = None
        self.api_internal_url_cache = None

        self.collectors = []

    @property
    def plus_status_internal_url(self):
        """
        Property that tracks back the plus_status_internal_url from the parent
        nginx object and caching it.  This cache works because child objects
        are stopped and unregistered when nginx objects are modified
        (restarted, etc.).
        """
        if not self.plus_status_internal_url_cache:
            parent_obj = context.objects.find_parent(obj_id=self.id)
            if parent_obj:
                self.plus_status_internal_url_cache = parent_obj.plus_status_internal_url
        return self.plus_status_internal_url_cache

    @property
    def api_internal_url(self):
        """
        Property that tracks back the plus_api_internal_url from the parent
        nginx object and caching it.  This cache works because child objects
        are stopped and unregistered when nginx objects are modified
        (restarted, etc.).
        """
        if not self.api_internal_url_cache:
            parent_obj = context.objects.find_parent(obj_id=self.id)
            if parent_obj:
                self.api_internal_url_cache = parent_obj.api_internal_url
        return self.api_internal_url_cache

    @property
    def definition(self):
        return {
            'type': self.type_template % self.type,
            'local_id': self.local_id,
            'root_uuid': self.root_uuid
        }

    @property
    def local_id_args(self):
        return self.parent_local_id, self.type, self.local_name
