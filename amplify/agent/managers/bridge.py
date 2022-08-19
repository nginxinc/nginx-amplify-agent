# -*- coding: utf-8 -*-
import gc
import time

from collections import deque
from requests.exceptions import HTTPError

from amplify.agent.common.context import context
from amplify.agent.common.cloud import HTTP503Error
from amplify.agent.common.util.backoff import exponential_delay
from amplify.agent.managers.abstract import AbstractManager


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class Bridge(AbstractManager):
    """
    Manager that flushes object bins and stores them in deques.  These deques are then sent to backend.
    """
    name = 'bridge_manager'

    def __init__(self, **kwargs):
        if 'interval' not in kwargs:
            kwargs['interval'] = context.app_config['cloud']['push_interval']
        super(Bridge, self).__init__(**kwargs)

        self.payload = {}
        self.first_run = True

        self.last_http_attempt = 0
        self.http_fail_count = 0
        self.http_delay = 0

        # Instantiate payload with appropriate keys and buckets.
        self._reset_payload()

    @staticmethod
    def look_around():
        """
        Checks everything around and make appropriate tree structure
        :return: dict of structure
        """
        # TODO check docker or OS around
        tree = {'system': ['nginx']}
        return tree

    def _run(self):
        try:
            self.flush_all()
            gc.collect()
        except:
            context.default_log.error('failed', exc_info=True)
            raise

    def flush_metrics(self):
        """
        Flushes only metrics
        """
        flush_data = self._flush_metrics()
        if flush_data:
            self.payload['metrics'].append(flush_data)
        self._send_payload()

    def flush_all(self, force=False):
        """
        Flushes all data
        """
        clients = {
            'meta': self._flush_meta,
            'metrics': self._flush_metrics,
            'events': self._flush_events,
            'configs': self._flush_configs
        }

        # Flush data and add to appropriate payload bucket.
        if self.first_run:
            # If this is the first run, flush meta only to ensure object creation.
            flush_data = self._flush_meta()
            if flush_data:
                self.payload['meta'].append(flush_data)
        else:
            for client_type in self.payload.keys():
                if client_type in clients:
                    flush_data = clients[client_type].__call__()
                    if flush_data:
                        self.payload[client_type].append(flush_data)

        now = time.time()
        if force or (
            now >= (self.last_http_attempt + self.interval + self.http_delay) and
            now > context.backpressure_time
        ):
            self._send_payload()

    def _send_payload(self):
        """
        Sends current payload to backend
        """
        context.log.debug(
            'modified payload; current payload stats: '
            'meta - %s, metrics - %s, events - %s, configs - %s' % (
                len(self.payload['meta']),
                len(self.payload['metrics']),
                len(self.payload['events']),
                len(self.payload['configs'])
            )
        )

        # Send payload to backend.
        try:
            self.last_http_attempt = time.time()

            self._pre_process_payload()  # Convert deques to lists for encoding
            context.http_client.post('update/', data=self.payload)
            context.default_log.debug(self.payload)
            self._reset_payload()  # Clear payload after successful

            if self.first_run:
                self.first_run = False  # Set first_run to False after first successful send

            if self.http_delay:
                self.http_fail_count = 0
                self.http_delay = 0  # Reset HTTP delay on success
                context.log.debug('successful update, reset http delay')
        except Exception as e:
            self._post_process_payload()  # Convert lists to deques since send failed

            if isinstance(e, HTTPError) and e.response.status_code == 503:
                backpressure_error = HTTP503Error(e)
                context.backpressure_time = int(time.time() + backpressure_error.delay)
                context.log.debug(
                    'back pressure delay %s added (next talk: %s)' % (
                        backpressure_error.delay,
                        context.backpressure_time
                    )
                )
            else:
                self.http_fail_count += 1
                self.http_delay = exponential_delay(self.http_fail_count)
                context.log.debug('http delay set to %s (fails: %s)' % (self.http_delay, self.http_fail_count))

            exception_name = e.__class__.__name__
            context.log.error('failed to push data due to %s' % exception_name)
            context.log.debug('additional info:', exc_info=True)

        context.log.debug(
            'finished flush_all; new payload stats: '
            'meta - %s, metrics - %s, events - %s, configs - %s' % (
                len(self.payload['meta']),
                len(self.payload['metrics']),
                len(self.payload['events']),
                len(self.payload['configs'])
            )
        )

    def _flush_meta(self):
        return self._flush(clients=['meta'])

    def _flush_metrics(self):
        return self._flush(clients=['metrics'])

    def _flush_events(self):
        return self._flush(clients=['events'])

    def _flush_configs(self):
        return self._flush(clients=['configs'])

    def _flush(self, clients=None):
        # get structure
        objects_structure = context.objects.tree()

        # recursive flush
        results = self._recursive_object_flush(objects_structure, clients=clients) if objects_structure else None
        return results

    @staticmethod
    def _empty_flush(flush_dict):
        """Helper for determining whether or not a flush payload is empty or not.  Checks to see if _any_ key other
        than object was included in the flush payload and assumes it is non-empty if so."""
        empty = True
        for key in flush_dict.keys():
            if key != 'object':
                empty = False
        return empty

    def _recursive_object_flush(self, tree, clients=None):
        results = {}

        object_flush = tree['object'].flush(clients=clients)
        if object_flush:
            results.update(object_flush)

        if tree['children']:
            children_results = []
            for child_tree in tree['children']:
                child_result = self._recursive_object_flush(child_tree, clients=clients)
                if child_result:
                    children_results.append(child_result)

            if children_results:
                results['children'] = children_results

        if not self._empty_flush(results):
            return results

    def _reset_payload(self):
        """
        After payload has been successfully sent, clear the queues (reset them to empty deques).
        """
        self.payload = {
            'meta': deque(maxlen=360),
            'metrics': deque(maxlen=360),
            'events': deque(maxlen=360),
            'configs': deque(maxlen=360)
        }

    def _pre_process_payload(self):
        """
        ujson.encode does not handle deque objects well.  So before attempting a send, convert all the deques to lists.
        """
        for key in self.payload.keys():
            self.payload[key] = list(self.payload[key])

    def _post_process_payload(self):
        """
        If a payload is NOT reset (cannot be sent), then we should reconvert the lists to deques with maxlen to enforce
        memory management.
        """
        for key in self.payload.keys():
            self.payload[key] = deque(self.payload[key], maxlen=360)
