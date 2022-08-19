# -*- coding: utf-8 -*-
from amplify.agent.collectors.abstract import AbstractCollector
from amplify.agent.objects.nginx.log.error import NginxErrorLogParser

from amplify.agent.common.context import context
from amplify.agent.pipelines.abstract import Pipeline
from amplify.agent.pipelines.file import FileTail
from amplify.agent.objects.nginx.config.config import ERROR_LOG_LEVELS

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class NginxErrorLogsCollector(AbstractCollector):
    short_name = 'nginx_elog'

    zero_counters = (
        'nginx.http.request.buffered',
        'nginx.upstream.response.buffered',
        'nginx.upstream.request.failed',
        'nginx.upstream.response.failed',
    )

    def __init__(self, filename=None, level=None, log_format=None, tail=None, **kwargs):
        super(NginxErrorLogsCollector, self).__init__(**kwargs)
        self.filename = filename
        self.level = level
        self.parser = NginxErrorLogParser()
        self.tail = tail if tail is not None else FileTail(filename)
        self.register(self.error_log_parsed)

    def collect(self):
        # If log_level is <= warn (e.g. debug, info, notice, warn)
        if ERROR_LOG_LEVELS.index(self.level) <= 3:
            self.init_counters()  # set all error counters to 0

        count = 0
        for line in self.tail:
            count += 1
            try:
                error = self.parser.parse(line)
            except:
                context.log.debug('could not parse line %r' % line, exc_info=True)
                error = None

            if error:
                super(NginxErrorLogsCollector, self).collect(error)

        tail_name = self.tail.name if isinstance(self.tail, Pipeline) else 'list'
        context.log.debug('%s processed %s lines from %s' % (self.object.definition_hash, count, tail_name))

    def error_log_parsed(self, error):
        self.object.statsd.incr(error)
