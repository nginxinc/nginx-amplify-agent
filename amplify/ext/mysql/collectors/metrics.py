# -*- coding: utf-8 -*-
import time

from amplify.agent.common.context import context
from amplify.agent.collectors.abstract import AbstractMetricsCollector

__author__ = "Andrew Alexeev"
__copyright__ = "Copyright (C) Nginx Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


METRICS = {
    'counters': {
        'mysql.global.connections': 'Connections',
        'mysql.global.questions': 'Questions',
        'mysql.global.select': 'Com_select',
        'mysql.global.insert': 'Com_insert',
        'mysql.global.update': 'Com_update',
        'mysql.global.delete': 'Com_delete',
        'mysql.global.commit': 'Com_commit',
        'mysql.global.slow_queries': 'Slow_queries',
        'mysql.global.uptime': 'Uptime',
        'mysql.global.aborted_connects': 'Aborted_connects',
        'mysql.global.innodb_buffer_pool_read_requests': 'Innodb_buffer_pool_read_requests',
        'mysql.global.innodb_buffer_pool_reads': 'Innodb_buffer_pool_reads'
    },
    'gauges': {
        'mysql.global.innodb_buffer_pool_pages_total': 'Innodb_buffer_pool_pages_total',
        'mysql.global.innodb_buffer_pool_pages_free': 'Innodb_buffer_pool_pages_free',
        'mysql.global.threads_connected': 'Threads_connected',
        'mysql.global.threads_running': 'Threads_running'
    }
}

REQUIRED_STATUS_FIELDS = list(METRICS['counters'].values()) + list(METRICS['gauges'].values())


class MySQLMetricsCollector(AbstractMetricsCollector):
    """
    Metrics collector.  Spawned per master.
    """
    short_name = 'mysql_metrics'
    status_metric_key = 'mysql.status'

    def __init__(self, **kwargs):
        super(MySQLMetricsCollector, self).__init__(**kwargs)

        self.register(
            self.mysql_status
        )

    def mysql_status(self):
        """
        Collects data from MySQLd instance

        """
        stamp = int(time.time())

        # get data
        conn = self.object.connect()
        result = {}
        try:
            with conn.cursor() as cursor:
                for key in REQUIRED_STATUS_FIELDS:
                    cursor.execute('SHOW GLOBAL STATUS LIKE "%s";' % key)
                    row = cursor.fetchone()
                    result[row[0]] = row[1]
        except Exception as e:
            exception_name = e.__class__.__name__
            context.log.debug('failed to collect MySQLd metrics due to %s' % exception_name)
            context.log.debug('additional info:', exc_info=True)
        finally:
            conn.close()

        # counters
        counted_vars = {}
        for metric, variable_name in METRICS['counters'].items():
            if variable_name in result:
                counted_vars[metric] = int(result[variable_name])

        # compound counter
        counted_vars['mysql.global.writes'] = \
            counted_vars['mysql.global.insert'] + \
            counted_vars['mysql.global.update'] + \
            counted_vars['mysql.global.delete']

        self.aggregate_counters(counted_vars, stamp=stamp)

        # gauges
        tracked_gauges = {}
        for metric, variable_name in METRICS['gauges'].items():
            if variable_name in result:
                tracked_gauges[metric] = {
                    self.object.definition_hash: int(result[variable_name])
                }

        # compound gauges
        pool_util = 0
        if ('mysql.global.innodb_buffer_pool_pages_total' in tracked_gauges and
                tracked_gauges['mysql.global.innodb_buffer_pool_pages_total'][self.object.definition_hash] > 0):
            pool_util = (
                (tracked_gauges['mysql.global.innodb_buffer_pool_pages_total'][self.object.definition_hash] -
                 tracked_gauges['mysql.global.innodb_buffer_pool_pages_free'][self.object.definition_hash]) /
                tracked_gauges['mysql.global.innodb_buffer_pool_pages_total'][self.object.definition_hash] * 100
            )
        tracked_gauges['mysql.global.innodb_buffer_pool_util'] = {
            self.object.definition_hash: pool_util
        }

        hit_ratio = 0
        if ('mysql.global.innodb_buffer_pool_read_requests' in tracked_gauges and
                tracked_gauges['mysql.global.innodb_buffer_pool_read_requests'][self.object.definition_hash] > 0):
            hit_ratio = (
                (tracked_gauges['mysql.global.innodb_buffer_pool_read_requests'][self.object.definition_hash] /
                 (tracked_gauges['mysql.global.innodb_buffer_pool_read_requests'][self.object.definition_hash] +
                  tracked_gauges['mysql.global.innodb_buffer_pool_reads'][self.object.definition_hash])) * 100
            )

        tracked_gauges['mysql.global.innodb_buffer_pool.hit_ratio'] = {
            self.object.definition_hash: hit_ratio
        }

        self.aggregate_gauges(tracked_gauges, stamp=stamp)

        # finalize
        self.increment_counters()
        self.finalize_gauges()
