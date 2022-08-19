# -*- coding: utf-8 -*-
import abc
from collections import defaultdict

from amplify.agent.common.context import context
from amplify.agent.objects.abstract import AbstractObject


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class AbstractExtObject(AbstractObject):
    type = 'abstract'

    def __init__(self, *args, **kwargs):
        super(AbstractExtObject, self).__init__(*args, **kwargs)

        _interval_dict = defaultdict(lambda: 10)
        _interval_dict['default'] = 10

        self.root_uuid = context.uuid
        self.intervals = context.app_config['containers'].get(self.type, {}).get('poll_intervals', _interval_dict)

    @abc.abstractproperty
    def local_id_args(self):
        """
        Abstract enforcement for SDK inherited objects.  These arguments are used to create the local_id hash used in
        the object definition hash.
        """
        return super(AbstractExtObject, self).local_id_args

    @property
    def definition(self):
        return {'type': self.type, 'local_id': self.local_id, 'root_uuid': self.root_uuid}
