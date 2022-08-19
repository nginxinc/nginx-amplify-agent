# -*- coding: utf-8 -*-
import time

from amplify.agent.collectors.abstract import AbstractCollector
from amplify.agent.common.context import context
from amplify.agent.pipelines.abstract import Pipeline
from amplify.agent.objects.nginx.log.access import NginxAccessLogParser
import copy


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class NginxAccessLogsCollector(AbstractCollector):
    short_name = 'nginx_alog'

    counters = {
        'nginx.http.method.head': 'request_method',
        'nginx.http.method.get': 'request_method',
        'nginx.http.method.post': 'request_method',
        'nginx.http.method.put': 'request_method',
        'nginx.http.method.delete': 'request_method',
        'nginx.http.method.options': 'request_method',
        'nginx.http.method.other': 'request_method',
        'nginx.http.status.1xx': 'status',
        'nginx.http.status.2xx': 'status',
        'nginx.http.status.3xx': 'status',
        'nginx.http.status.4xx': 'status',
        'nginx.http.status.403': 'status',
        'nginx.http.status.404': 'status',
        'nginx.http.status.5xx': 'status',
        'nginx.http.status.500': 'status',
        'nginx.http.status.502': 'status',
        'nginx.http.status.503': 'status',
        'nginx.http.status.504': 'status',
        'nginx.http.status.discarded': 'status',
        'nginx.http.v0_9': 'server_protocol',
        'nginx.http.v1_0': 'server_protocol',
        'nginx.http.v1_1': 'server_protocol',
        'nginx.http.v2': 'server_protocol',
        'nginx.http.request.body_bytes_sent': 'body_bytes_sent',
        'nginx.http.request.bytes_sent': 'bytes_sent',
        'nginx.upstream.status.1xx': 'upstream_status',
        'nginx.upstream.status.2xx': 'upstream_status',
        'nginx.upstream.status.3xx': 'upstream_status',
        'nginx.upstream.status.4xx': 'upstream_status',
        'nginx.upstream.status.5xx': 'upstream_status',
        'nginx.cache.bypass': 'upstream_cache_status',
        'nginx.cache.expired': 'upstream_cache_status',
        'nginx.cache.hit': 'upstream_cache_status',
        'nginx.cache.miss': 'upstream_cache_status',
        'nginx.cache.revalidated': 'upstream_cache_status',
        'nginx.cache.stale': 'upstream_cache_status',
        'nginx.cache.updating': 'upstream_cache_status',
        'nginx.upstream.next.count': None,
        'nginx.upstream.request.count': None
    }

    valid_http_methods = (
        'head',
        'get',
        'post',
        'put',
        'delete',
        'options'
    )

    valid_cache_statuses = (
        'bypass',
        'expired',
        'hit',
        'miss',
        'revalidated',
        'stale',
        'updating',
    )

    def __init__(self, log_format=None, tail=None, **kwargs):
        super(NginxAccessLogsCollector, self).__init__(**kwargs)
        self.parser = NginxAccessLogParser(log_format)
        self.num_of_lines_in_log_format = self.parser.raw_format.count('\n')+1
        self.tail = tail
        # syslog tails names are "<type>:<name>"
        self.name = tail.name.split(':')[-1] if isinstance(tail, Pipeline) \
            else None
        self.filters = []

        # skip empty filters and filters for other log file
        for log_filter in self.object.filters:
            if log_filter.empty:
                continue
            if not log_filter.matchfile(self.name):
                continue
            self.filters.append(log_filter)

        self.register(
            self.http_method,
            self.http_status,
            self.http_version,
            self.request_length,
            self.body_bytes_sent,
            self.bytes_sent,
            self.gzip_ration,
            self.request_time,
            self.upstreams,
        )

    def init_counters(self, counters=None):
        for counter, key in self.counters.items():
            # If keys are in the parser format (access log) or not defined (error log)
            if key in self.parser.keys or key is None:
                self.object.statsd.incr(counter, value=0)

        # init counters for custom filters
        for counter in set(f.metric for f in self.filters):
            if counter in self.counters:
                self.count_custom_filter(self.filters, counter, 0, self.object.statsd.incr)

    def collect(self):
        self.init_counters()  # set all counters to 0

        count = 0
        multiline_record = []
        for line in self.tail:
            count += 1

            # release GIL every 1000 of lines
            if count % (1000 * self.num_of_lines_in_log_format) == 0:
                time.sleep(0.001)

            # handle multiline log formats
            if self.num_of_lines_in_log_format > 1:
                multiline_record.append(line)
                if len(multiline_record) < self.num_of_lines_in_log_format:
                    continue
                else:
                    line = '\n'.join(multiline_record)
                    multiline_record = []

            try:
                parsed = self.parser.parse(line)
            except:
                context.log.debug('could not parse line %r' % line, exc_info=True)
                parsed = None

            if not parsed:
                continue

            if parsed['malformed']:
                self.request_malformed()
            else:
                # try to match custom filters and collect log metrics with them
                matched_filters = [filter for filter in self.filters if filter.match(parsed)]
                super(NginxAccessLogsCollector, self).collect(parsed, matched_filters)

        tail_name = self.tail.name if isinstance(self.tail, Pipeline) else 'list'
        context.log.debug('%s processed %s lines from %s' % (self.object.definition_hash, count, tail_name))

    def request_malformed(self):
        """
        nginx.http.request.malformed
        """
        self.object.statsd.incr('nginx.http.request.malformed')

    def http_method(self, data, matched_filters=None):
        """
        nginx.http.method.head
        nginx.http.method.get
        nginx.http.method.post
        nginx.http.method.put
        nginx.http.method.delete
        nginx.http.method.options
        nginx.http.method.other

        :param data: {} of parsed line
        :param matched_filters: [] of matched filters
        """
        if 'request_method' in data:
            method = data['request_method'].lower()
            method = method if method in self.valid_http_methods else 'other'
            metric_name = 'nginx.http.method.%s' % method
            self.object.statsd.incr(metric_name)
            if matched_filters:
                self.count_custom_filter(matched_filters, metric_name, 1, self.object.statsd.incr)

    def http_status(self, data, matched_filters=None):
        """
        nginx.http.status.1xx
        nginx.http.status.2xx
        nginx.http.status.3xx
        nginx.http.status.4xx
        nginx.http.status.403
        nginx.http.status.404
        nginx.http.status.5xx
        nginx.http.status.500
        nginx.http.status.502
        nginx.http.status.503
        nginx.http.status.504
        nginx.http.status.discarded

        :param data: {} of parsed line
        :param matched_filters: [] of matched filters
        """
        if 'status' in data:
            metrics_to_populate = []
            http_status = data['status']

            # add separate metrics for specific 4xx and 5xx codes
            if http_status.startswith('4'):
                if http_status in ('403', '404'):
                    metrics_to_populate.append('nginx.http.status.%s' % http_status)
            elif http_status.startswith('5'):
                if http_status in ('500', '502', '503', '504'):
                    metrics_to_populate.append('nginx.http.status.%s' % http_status)

            metrics_to_populate.append('nginx.http.status.%sxx' % http_status[0])

            for metric_name in metrics_to_populate:
                self.object.statsd.incr(metric_name)
                if matched_filters:
                    self.count_custom_filter(matched_filters, metric_name, 1, self.object.statsd.incr)

                if data['status'] == '499':
                    metric_name = 'nginx.http.status.discarded'
                    self.object.statsd.incr(metric_name)
                    if matched_filters:
                        self.count_custom_filter(matched_filters, metric_name, 1, self.object.statsd.incr)

    def http_version(self, data, matched_filters=None):
        """
        nginx.http.v0_9
        nginx.http.v1_0
        nginx.http.v1_1
        nginx.http.v2

        :param data: {} of parsed line
        :param matched_filters: [] of matched filters
        """
        if 'server_protocol' in data:
            proto = data['server_protocol']
            if not proto.startswith('HTTP'):
                return

            version = proto.split('/')[-1]

            # Ordered roughly by expected popularity to reduce number of calls to `startswith`
            if version.startswith('1.1'):
                suffix = '1_1'
            elif version.startswith('2.0'):
                suffix = '2'
            elif version.startswith('1.0'):
                suffix = '1_0'
            elif version.startswith('0.9'):
                suffix = '0_9'
            else:
                suffix = version.replace('.', '_')

            metric_name = 'nginx.http.v%s' % suffix
            self.object.statsd.incr(metric_name)
            if matched_filters:
                self.count_custom_filter(matched_filters, metric_name, 1, self.object.statsd.incr)

    def request_length(self, data, matched_filters=None):
        """
        nginx.http.request.length

        :param data: {} of parsed line
        :param matched_filters: [] of matched filters
        """
        if 'request_length' in data:
            metric_name, value = 'nginx.http.request.length', data['request_length']
            self.object.statsd.average(metric_name, value)
            if matched_filters:
                self.count_custom_filter(matched_filters, metric_name, value, self.object.statsd.average)

    def body_bytes_sent(self, data, matched_filters=None):
        """
        nginx.http.request.body_bytes_sent

        :param data: {} of parsed line
        :param matched_filters: [] of matched filters
        """
        if 'body_bytes_sent' in data:
            metric_name, value = 'nginx.http.request.body_bytes_sent', data['body_bytes_sent']
            self.object.statsd.incr(metric_name, value)
            if matched_filters:
                self.count_custom_filter(matched_filters, metric_name, value, self.object.statsd.incr)

    def bytes_sent(self, data, matched_filters=None):
        """
        nginx.http.request.bytes_sent

        :param data: {} of parsed line
        :param matched_filters: [] of matched filters
        """
        if 'bytes_sent' in data:
            metric_name, value = 'nginx.http.request.bytes_sent', data['bytes_sent']
            self.object.statsd.incr(metric_name, value)
            if matched_filters:
                self.count_custom_filter(matched_filters, metric_name, value, self.object.statsd.incr)

    def gzip_ration(self, data, matched_filters=None):
        """
        nginx.http.gzip.ratio

        :param data: {} of parsed line
        :param matched_filters: [] of matched filters
        """
        if 'gzip_ratio' in data:
            metric_name, value = 'nginx.http.gzip.ratio', data['gzip_ratio']
            self.object.statsd.average(metric_name, value)
            if matched_filters:
                self.count_custom_filter(matched_filters, metric_name, value, self.object.statsd.average)

    def request_time(self, data, matched_filters=None):
        """
        nginx.http.request.time
        nginx.http.request.time.median
        nginx.http.request.time.max
        nginx.http.request.time.pctl95
        nginx.http.request.time.count

        :param data: {} of parsed line
        :param matched_filters: [] of matched filters
        """
        if 'request_time' in data:
            metric_name, value = 'nginx.http.request.time', sum(data['request_time'])
            self.object.statsd.timer(metric_name, value)
            if matched_filters:
                self.count_custom_filter(self.create_parent_filters(matched_filters, parent_metric=metric_name),
                                         metric_name, value,
                                         self.object.statsd.timer)

    def upstreams(self, data, matched_filters=None):
        """
        nginx.cache.bypass
        nginx.cache.expired
        nginx.cache.hit
        nginx.cache.miss
        nginx.cache.revalidated
        nginx.cache.stale
        nginx.cache.updating
        nginx.upstream.request.count
        nginx.upstream.next.count
        nginx.upstream.connect.time
        nginx.upstream.connect.time.median
        nginx.upstream.connect.time.max
        nginx.upstream.connect.time.pctl95
        nginx.upstream.connect.time.count
        nginx.upstream.header.time
        nginx.upstream.header.time.median
        nginx.upstream.header.time.max
        nginx.upstream.header.time.pctl95
        nginx.upstream.header.time.count
        nginx.upstream.response.time
        nginx.upstream.response.time.median
        nginx.upstream.response.time.max
        nginx.upstream.response.time.pctl95
        nginx.upstream.response.time.count
        nginx.upstream.status.1xx
        nginx.upstream.status.2xx
        nginx.upstream.status.3xx
        nginx.upstream.status.4xx
        nginx.upstream.status.5xx
        nginx.upstream.response.length

        :param data: {} of parsed line
        :param matched_filters: [] of matched filters
        """
        if not any(key.startswith('upstream') and data[key] not in ('-', '') for key in data):
            return

        # counters
        upstream_response = False
        if 'upstream_status' in data:
            for status in data['upstream_status']:  # upstream_status is parsed as a list
                if status.isdigit():
                    suffix = '%sxx' % status[0]
                    metric_name = 'nginx.upstream.status.%s' % suffix
                    upstream_response = True if suffix in ('2xx', '3xx') else False   # Set flag for upstream length processing
                    self.object.statsd.incr(metric_name)
                    if matched_filters:
                        self.count_custom_filter(matched_filters, metric_name, 1, self.object.statsd.incr)

        if upstream_response and 'upstream_response_length' in data:
            metric_name, value = 'nginx.upstream.response.length', data['upstream_response_length']
            self.object.statsd.average(metric_name, value)
            if matched_filters:
                self.count_custom_filter(matched_filters, metric_name, value, self.object.statsd.average)

        # gauges
        upstream_switches = None
        for metric_name, key_name in {
            'nginx.upstream.connect.time': 'upstream_connect_time',
            'nginx.upstream.response.time': 'upstream_response_time',
            'nginx.upstream.header.time': 'upstream_header_time'
        }.items():
            if key_name in data:
                values = data[key_name]

                # set upstream switches one time
                if len(values) > 1 and upstream_switches is None:
                    upstream_switches = len(values) - 1

                # store all values
                value = sum(values)
                self.object.statsd.timer(metric_name, value)
                if matched_filters:
                    self.count_custom_filter(self.create_parent_filters(matched_filters, parent_metric=metric_name),
                                             metric_name,
                                             value, self.object.statsd.timer)

        # log upstream switches
        metric_name, value = 'nginx.upstream.next.count', 0 if upstream_switches is None else upstream_switches
        self.object.statsd.incr(metric_name, value)
        if matched_filters:
            self.count_custom_filter(matched_filters, metric_name, value, self.object.statsd.incr)

        # cache
        if 'upstream_cache_status' in data:
            cache_status = data['upstream_cache_status']
            cache_status_lower = cache_status.lower()
            if cache_status_lower in self.valid_cache_statuses:
                metric_name = 'nginx.cache.%s' % cache_status_lower
                self.object.statsd.incr(metric_name)
                if matched_filters:
                    self.count_custom_filter(matched_filters, metric_name, 1, self.object.statsd.incr)

        # log total upstream requests
        metric_name = 'nginx.upstream.request.count'
        self.object.statsd.incr(metric_name)
        if matched_filters:
            self.count_custom_filter(matched_filters, metric_name, 1, self.object.statsd.incr)

    @staticmethod
    def create_parent_filters(original_filters, parent_metric):
        """
        median, max, pctl95, and count are created in statsd.flush().  So if a
        filter on nginx.upstream.response.time.median is created, the filter metric
        should be truncated to nginx.upstream.response.time

        :param original_filters:
        :param truncated_metric:
        :return:
        """
        parent_filters = []
        for original_filter in original_filters:
            if parent_metric not in original_filter.metric:
                continue
            parent_filter = copy.deepcopy(original_filter)
            parent_filter.metric = parent_metric
            parent_filters.append(parent_filter)
        return parent_filters

    @staticmethod
    def count_custom_filter(matched_filters, metric_name, value, method):
        """
        Collect custom metric

        :param matched_filters: [] of matched filters
        :param metric_name: str metric name
        :param value: int/float value
        :param method: function to call
        :return:
        """
        for log_filter in matched_filters:
            if log_filter.metric == metric_name:
                full_metric_name = '%s||%s' % (log_filter.metric, log_filter.filter_rule_id)
                method(full_metric_name, value)
