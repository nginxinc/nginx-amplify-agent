# -*- coding: utf-8 -*-
import copy

from amplify.agent.collectors.abstract import AbstractMetricsCollector
from amplify.agent.common.context import context

__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class PlusStatusCollector(AbstractMetricsCollector):
    """
    Common Plus status collector.  Collects data from parent object plus status cache.
    """
    short_name = "plus_status"
    collect_index = []

    def __init__(self, *args, **kwargs):
        super(PlusStatusCollector, self).__init__(*args, **kwargs)
        self.last_collect = -1
        self.register(*self.collect_index)

    def gather_data(self, area=None, name=None):
        """
        Common data gathering method.  This method will open the stored Plus status JSON payload, navigate to the proper
        area (e.g. 'upstreams', 'server_zones', 'caches') and specific named object (e.g. 'http_cache') and grab the
        data structure.

        Only gathers data since last collect.

        :param area: Str
        :param name: Str
        :return: List Zipped tuples of data, stamp in order of oldest first.
        """
        if not area:
            area = '%ss' % self.object.type

        if not name:
            name = self.object.local_name

        data = []
        stamps = []

        try:
            for status, stamp in reversed(context.plus_cache[self.object.plus_status_internal_url]):
                if stamp > self.last_collect:
                    data.append(copy.deepcopy(status[area][name]))
                    stamps.append(stamp)
                else:
                    break  # We found the last collected payload
        except:
            context.default_log.error('%s collector gather data failed' % self.object.definition_hash, exc_info=True)
            raise

        if data and stamps:
            self.last_collect = stamps[0]

        return zip(reversed(data), reversed(stamps))  # Stamps are gathered here for future consideration.

    def collect(self):
        try:
            for data, stamp in self.gather_data():
                self.collect_from_data(data, stamp)
                try:
                    self.increment_counters()
                except Exception as e:
                    self.handle_exception(self.increment_counters, e)

        except Exception as e:
            self.handle_exception(self.gather_data, e)

    def collect_from_data(self, data, stamp):
        """
        Defines what plus status collectors should do with each (data, stamp) tuple returned from gather_data
        """
        super(PlusStatusCollector, self).collect(self, data, stamp)


class PlusAPICollector(AbstractMetricsCollector):
    """
    Common Plus API Collector.  Collects data from parent object plus api cache
    """
    short_name = "plus_api"
    collect_index = []
    api_payload_path = []

    def __init__(self, *args, **kwargs):
        super(PlusAPICollector, self).__init__(*args, **kwargs)
        self.last_collect = -1
        self.register(*self.collect_index)

    def gather_data(self):

        data = []
        stamps = []

        try:
            for api_payload, stamp in reversed(context.plus_cache[self.object.api_internal_url]):
                if stamp > self.last_collect:
                    api_sub_payload = api_payload
                    for subarea in self.api_payload_path:
                        api_sub_payload = api_sub_payload[subarea]
                    data.append(copy.deepcopy(api_sub_payload[self.object.local_name]))
                    stamps.append(stamp)
                else:
                    break
        except:
            context.default_log.error('%s collector gather data failed' % self.object.definition_hash, exc_info=True)

        if data and stamps:
            self.last_collect = stamps[0]

        return zip(reversed(data), reversed(stamps))

    def collect(self):
        try:
            for data, stamp in self.gather_data():
                self.collect_from_data(data, stamp)
                try:
                    self.increment_counters()
                except Exception as e:
                    self.handle_exception(self.increment_counters, e)

        except Exception as e:
            self.handle_exception(self.gather_data, e)

    def collect_from_data(self, data, stamp):
        """
        Defines what plus status collectors should do with each (data, stamp) tuple returned from gather_data
        """
        super(PlusAPICollector, self).collect(self, data, stamp)

