# -*- coding: utf-8 -*-
import copy
import time

from amplify.agent.common.util.math import median
from collections import defaultdict

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class StatsdClient(object):
    def __init__(self, address=None, port=None, interval=None, object=None):
        # Import context as a class object to avoid circular import on statsd.  This could be refactored later.
        from amplify.agent.common.context import context
        self.context = context

        self.address = address
        self.port = port
        self.object = object
        self.interval = interval
        self.current = defaultdict(dict)
        self.delivery = defaultdict(dict)

    def latest(self, metric_name, value, stamp=None):
        """
        Stores the most recent value of a gauge

        :param metric_name: metric name
        :param value: metric value
        :param stamp: timestamp (current timestamp will be used if this is not specified)
        """
        timestamp = stamp or int(time.time())
        gauges = self.current['gauge']
        if metric_name not in gauges or timestamp > gauges[metric_name][0][0]:
            gauges[metric_name] = [(timestamp, value)]

    def average(self, metric_name, value):
        """
        Same thing as histogram but without p95

        :param metric_name:  metric name
        :param value:  metric value
        """
        if metric_name in self.current['average']:
            self.current['average'][metric_name].append(value)
        else:
            self.current['average'][metric_name] = [value]

    def timer(self, metric_name, value):
        """
        Histogram with 95 percentile

        The algorithm is as follows:

        Collect all the data samples for a period of time (commonly a day, a week, or a month).
        Sort the data set by value from highest to lowest and discard the highest 5% of the sorted samples.
        The next highest sample is the 95th percentile value for the data set.

        :param metric_name: metric name
        :param value: metric value
        """
        if metric_name in self.current['timer']:
            self.current['timer'][metric_name].append(value)
        else:
            self.current['timer'][metric_name] = [value]

    def incr(self, metric_name, value=None, rate=None, stamp=None):
        """
        Simple counter with rate

        :param metric_name: metric name
        :param value: metric value
        :param rate: rate
        :param stamp: timestamp (current timestamp will be used if this is not specified)
        """
        timestamp = stamp or int(time.time())

        if value is None:
            value = 1
        elif value < 0:
            self.context.default_log.debug(
                'negative delta (%s) passed for metric %s, skipping' %
                (value, metric_name)
            )
            return

        # new metric
        if metric_name not in self.current['counter']:
            self.current['counter'][metric_name] = [[timestamp, value]]
            return

        # metric exists
        slots = self.current['counter'][metric_name]
        last_stamp, last_value = slots[-1]

        # if rate is set then check it's time
        if self.interval and rate:
            sample_duration = self.interval * rate
            # write to current slot
            if timestamp < last_stamp + sample_duration:
                self.current['counter'][metric_name][-1] = [last_stamp, last_value + value]
            else:
                self.current['counter'][metric_name].append([last_stamp, value])
        else:
            self.current['counter'][metric_name][-1] = [last_stamp, last_value + value]

    def object_status(self, metric_name, value=1, stamp=None):
        """
        Object status metrics
        :param metric_name: metric
        :param value: value
        :param stamp: timestamp (current timestamp will be used if this is not specified)
        """
        timestamp = stamp or int(time.time())
        self.current['gauge'][metric_name] = [(timestamp, value)]

    def gauge(self, metric_name, value, delta=False, prefix=False, stamp=None):
        """
        Gauge
        :param metric_name: metric name
        :param value: metric value
        :param delta: metric delta (applicable only if we have previous values)
        :param stamp: timestamp (current timestamp will be used if this is not specified)
        """
        timestamp = stamp or int(time.time())

        if metric_name in self.current['gauge']:
            if delta:
                last_stamp, last_value = self.current['gauge'][metric_name][-1]
                new_value = last_value + value
            else:
                new_value = value
            self.current['gauge'][metric_name].append((timestamp, new_value))
        else:
            self.current['gauge'][metric_name] = [(timestamp, value)]

    def flush(self):
        if not self.current:
            return {'object': self.object.definition}

        results = {}
        delivery = copy.deepcopy(self.current)
        self.current = defaultdict(dict)

        # histogram
        if 'timer' in delivery:
            timers = {}
            timestamp = int(time.time())
            for metric_name, metric_values in delivery['timer'].items():
                if len(metric_values):
                    metric_values.sort()
                    length = len(metric_values)
                    timers['G|%s' % metric_name] = [[timestamp, sum(metric_values) / float(length)]]
                    filter_suffix = ""
                    filter_suffix_index = metric_name.find("||")
                    if filter_suffix_index > 0:
                        filter_suffix = metric_name[filter_suffix_index:]
                        metric_name = metric_name[:filter_suffix_index]
                    timers['C|%s.count%s' % (metric_name, filter_suffix)] = [[timestamp, length]]
                    timers['G|%s.max%s' % (metric_name, filter_suffix)] = [[timestamp, metric_values[-1]]]
                    timers['G|%s.median%s' % (metric_name, filter_suffix)] = [[timestamp, median(metric_values, presorted=True)]]
                    timers['G|%s.pctl95%s' % (metric_name, filter_suffix)] = [[timestamp, metric_values[-int(round(length * .05))]]]
            results['timer'] = timers

        # counters
        if 'counter' in delivery:
            counters = {}
            for k, v in delivery['counter'].items():
                # Aggregate all observed counters into a single record.
                last_stamp = v[-1][0]  # Use the oldest timestamp.
                total_value = 0
                for timestamp, value in v:
                    total_value += value

                # Condense the list of lists 'v' into a list of a single element.  Remember that we are using lists
                # instead of tuples because we need mutability during self.incr().
                counters['C|%s' % k] = [[last_stamp, total_value]]

            results['counter'] = counters

        # gauges
        if 'gauge' in delivery:
            gauges = {}
            for k, v in delivery['gauge'].items():
                # Aggregate all observed gauges into a single record.
                last_stamp = v[-1][0]  # Use the oldest timestamp.
                total_value = 0
                for timestamp, value in v:
                    total_value += value

                # Condense list of tuples 'v' into a list of a single tuple using an average value.
                gauges['G|%s' % k] = [(last_stamp, float(total_value)/len(v))]
            results['gauge'] = gauges

        # avg
        if 'average' in delivery:
            averages = {}
            timestamp = int(time.time())  # Take a new timestamp here because it is not collected previously.
            for metric_name, metric_values in delivery['average'].items():
                if len(metric_values):
                    length = len(metric_values)
                    averages['G|%s' % metric_name] = [[timestamp, sum(metric_values) / float(length)]]
            results['average'] = averages

        return {
            'metrics': copy.deepcopy(results),
            'object': self.object.definition
        }
