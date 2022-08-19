# -*- coding: utf-8 -*-
import copy

import pymysql

from amplify.agent.common.context import context
from amplify.agent.common.util.host import hostname
from amplify.ext.abstract.object import AbstractExtObject
from amplify.ext.mysql.collectors.meta import MySQLMetaCollector
from amplify.ext.mysql.collectors.metrics import MySQLMetricsCollector

__author__ = "Andrew Alexeev"
__copyright__ = "Copyright (C) Nginx Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class MySQLObject(AbstractExtObject):
    type = 'mysql'

    def __init__(self, **kwargs):
        super(MySQLObject, self).__init__(**kwargs)

        self.name = 'mysql'

        # cached values
        self._local_id = self.data.get('local_id', None)

        # attributes
        self.pid = self.data['pid']
        self.cmd = self.data['cmd']
        self.conf_path = self.data['conf_path']

        # connection args - for now we're reading them from agent conf
        self._setup_connection_args()

        # state
        self.parsed_conf = None
        self.parsed = False

        # collectors
        self._setup_meta_collector()
        self._setup_metrics_collector()

    @property
    def display_name(self):
        # override abstract version for user-friendliness.
        return "mysql @ %s" % hostname()

    @property
    def local_id_args(self):
        return self.cmd, self.conf_path

    def _setup_connection_args(self):
        connection_args = context.app_config.get('mysql', None)

        if connection_args is not None:
            if 'port' in connection_args:
                connection_args['port'] = int(connection_args['port'])

        self.connection_args = connection_args

    def _setup_meta_collector(self):
        self.collectors.append(
            MySQLMetaCollector(object=self, interval=self.intervals['meta'])
        )

    def _setup_metrics_collector(self):
        self.collectors.append(
            MySQLMetricsCollector(object=self, interval=self.intervals['metrics'])
        )

    def connect(self):
        """
        Connect to mysql with pymysql.
        """
        conn_kwargs = copy.deepcopy(context.app_config['mysql'])
        conn_kwargs.pop('remote', None)
        # open a connection
        try:
            return pymysql.connect(**conn_kwargs)
        except Exception as e:
            exception_name = e.__class__.__name__
            context.log.debug('failed to connect to MySQLd due to %s' % exception_name)
            context.log.debug('additional info:', exc_info=True)
            raise
