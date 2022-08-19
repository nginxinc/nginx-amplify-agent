# -*- coding: utf-8 -*-
import re

from amplify.agent.common.context import context
from amplify.agent.common.util.host import hostname
from amplify.ext.abstract.object import AbstractExtObject

from amplify.ext.phpfpm.collectors.pool.meta import PHPFPMPoolMetaCollector
from amplify.ext.phpfpm.collectors.pool.metrics import PHPFPMPoolMetricsCollector


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


_LISTEN_RE = re.compile(r'(\$\w+)')


class PHPFPMPoolObject(AbstractExtObject):
    type = 'phpfpm_pool'

    def __init__(self, **kwargs):
        super(PHPFPMPoolObject, self).__init__(**kwargs)

        # cached values
        self._local_id = self.data.get('local_id')
        self._flisten = None

        # attributes
        self.file = self.data['file']
        self.parent_local_id = self.data['parent_local_id']
        self.listen = self.data['listen']
        self.status_path = self.data['status_path']

        # collectors
        self._setup_meta_collector()
        self._setup_metrics_collector()

    @property
    def local_id_args(self):
        return self.parent_local_id, self.name

    @property
    def display_name(self):
        # override abstract version for user-friendliness.
        return "phpfpm %s @ %s" % (self.name, hostname())

    @property
    def flisten(self):
        """
        This is a helper to take raw "listen" strings from phpfpm configs and attempt to format them into something
        usable.  This is primarily the replacing of "$pool" variable.
        """
        if self._flisten is not None:
            return self._flisten

        SUPPORTED_VARS = {
            '$pool': self.name,
        }

        formatted_listen = self.listen

        for m in _LISTEN_RE.finditer(self.listen):
            fpm_var = m.group(1)  # e.g. "$pool"

            if fpm_var in SUPPORTED_VARS:
                formatted_listen = formatted_listen.replace(fpm_var, SUPPORTED_VARS[fpm_var])
            else:
                context.log.debug(
                    'found unsupported phpfpm conf variable "%s" in "%s" pool listen: "%s"' %
                    (fpm_var, self.name, self.listen)
                )

        self._flisten = formatted_listen

        return self._flisten

    def _setup_meta_collector(self):
        self.collectors.append(
            PHPFPMPoolMetaCollector(object=self, interval=self.intervals['meta'])
        )

    def _setup_metrics_collector(self):
        self.collectors.append(
            PHPFPMPoolMetricsCollector(object=self, interval=self.intervals['metrics'])
        )
