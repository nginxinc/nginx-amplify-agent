# -*- coding: utf-8 -*-
import abc
import hashlib
import time

from gevent import queue

try:
    from gevent.hub import BlockingSwitchOutError
except ImportError:
    # if using an old version of gevent (because this is running on CentOS 6) then
    # create a BlockingSwitchOutError class just to avoid raising NameErrors
    class BlockingSwitchOutError(Exception):
        pass

from amplify.agent.data.eventd import EventdClient
from amplify.agent.data.metad import MetadClient
from amplify.agent.data.statsd import StatsdClient

from amplify.agent.data.configd import ConfigdClient
from amplify.agent.common.context import context
from amplify.agent.common.util.threads import spawn
from amplify.agent.common.util import host, loader

from amplify.agent.pipelines.abstract import Pipeline

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class AbstractObject(object):
    """
    Abstract object. Supervisor for collectors and data client bucket.
    """

    # TODO: Refactor our agent objects to be more inline with our backend representations of the same.
    type = 'common'

    def __init__(self, data=None, **kwargs):
        self.id = None
        self.data = data if data else kwargs

        self.in_container = bool(context.app_config['credentials']['imagename'])
        self.intervals = context.app_config['containers'].get(self.type, {}).get('poll_intervals', {'default': 10})
        self.running = False
        self.need_restart = False
        self.init_time = int(time.time())

        self.threads = []
        self.collectors = []
        self.filters = []
        self.queue = queue.Queue()

        # data clients
        self.statsd = StatsdClient(object=self, interval=max(self.intervals.values()))
        self.eventd = EventdClient(object=self)
        self.metad = MetadClient(object=self)
        self.configd = self.data.get('configd', ConfigdClient(object=self))
        # configd is checked for in data so it can be passed between objects at the manger level.  This avoids excess
        # config parsing in nginx objects.
        self.clients = {
            'meta': self.metad,
            'metrics': self.statsd,
            'events': self.eventd,
            'configs': self.configd,
        }  # This is a client mapping to aid with lookup during flush by Bridge.

        self._definition_hash = None
        self._local_id = None

        self.name = self.data.get('name', None)

    @abc.abstractproperty
    def definition(self):
        return {'id': self.id, 'type': self.type}

    @property
    def definition_healthy(self):
        check = {}
        for k, v in self.definition.items():
            if v:
                check[k] = v
        return check == self.definition

    @property
    def definition_hash(self):
        if not self._definition_hash:
            definition_string = str(list(map(lambda x: u'%s:%s' % (x, self.definition[x]), sorted(list(self.definition.keys()))))).encode('utf-8')
            self._definition_hash = hashlib.sha256(definition_string).hexdigest()
        return self._definition_hash

    @staticmethod
    def hash(definition):
        definition_string = str(list(map(lambda x: u'%s:%s' % (x, definition[x]), sorted(list(definition.keys()))))).encode('utf-8')
        result = hashlib.sha256(definition_string).hexdigest()
        return result

    @property
    def local_id_args(self):
        """
        Class specific local_id_args for local_id hash.  Should be overridden by objects that utilize local_id's.
        (Optional for system/root objects)
        (Order sensitive)

        :return: Tuple String arguments to be used in string hashable
        """
        return tuple()

    @property
    def local_id(self):
        """
        This property will use assigned local_id (from self.local_id_cache) if one exists or construct one from the
        tuple of arguments returned by self.local_id_args.

        :return: String Hash representation of local_id.
        """
        # TODO: Refactor Nginx object to use this style local_id property.
        if not self._local_id and len(self.local_id_args):
            args = map(lambda x: str(x.encode('utf-8') if hasattr(x, 'encode') else x), self.local_id_args)
            self._local_id = hashlib.sha256('_'.join(args).encode('utf-8')).hexdigest()
        return self._local_id

    @staticmethod
    def hash_local(*local_id_args):
        """
        Helper for hashing passed arguments in local_id style.  Helpful for lookup/hash comparisons.

        :param local_id_args: List Ordered arguments for local_id hash
        :return: String 64 len hash of local_id
        """
        if len(local_id_args):
            args = map(lambda x: str(x.encode('utf-8') if hasattr(x, 'encode') else x), local_id_args)
            return hashlib.sha256('_'.join(args).encode('utf-8')).hexdigest()

    @property
    def display_name(self):
        """
        Generic attribute wrapper for returning a user-friendly/frontend label for an object.
        """

        # TOOD: We should clean up and unify our container detection.
        sysidentifier = context.app_config['credentials']['imagename'] or context.hostname

        if self.name is not None:
            return "%s %s @ %s" % (self.type, self.name, sysidentifier)
        else:
            return "%s @ %s" % (self.type, sysidentifier)

    def start(self):
        """
        Starts all of the object's collector threads
        """
        if not self.running:
            context.log.debug('starting object "%s" %s' % (self.type, self.definition_hash))
            for collector in self.collectors:
                self.threads.append(spawn(collector.run))
            self.running = True

    def stop(self):
        if self.running:
            context.log.debug('stopping object "%s" %s' % (self.type, self.definition_hash))
            for thread in self.threads:
                try:
                    thread.kill()
                except BlockingSwitchOutError:
                    pass
                except Exception as e:
                    context.log.debug('exception during object stop: {}'.format(e.__class__.__name__), exc_info=True)

            # For every collector, if the collector has a .tail attribute and is a Pipeline, send a stop signal.
            for collector in self.collectors:
                try:
                    if hasattr(collector, 'tail') and isinstance(collector.tail, Pipeline):
                        collector.tail.stop()
                except BlockingSwitchOutError:
                    pass
                except Exception as e:
                    context.log.debug('exception during pipeline stop', exc_info=True)

            self.running = False
            context.log.debug('stopped object "%s" %s ' % (self.type, self.definition_hash))

    def _import_collector_class(self, type, target):
        """
        Import a collector class

        :param type: str - Object type name (e.g. 'system' or 'nginx')
        :param target: str - what to collect (e.g. 'meta' or 'metrics')
        :return: A collector class that corresponds with the host's distribution
        """
        distribution = host.linux_name()
        distribution = {
            'ubuntu': '',
            'amzn': 'centos',
            'rhel': 'centos',
            'fedora': 'centos',
            'sles': 'centos'
        }.get(distribution, distribution)

        try:
            class_name = distribution.title() + type.title() + target.title() + 'Collector'
            class_path = 'amplify.agent.collectors.%s.%s.%s' % (type.lower(), target.lower(), class_name)
            cls = loader.import_class(class_path)
        except AttributeError:
            class_name = 'GenericLinux' + type.title() + target.title() + 'Collector'
            class_path = 'amplify.agent.collectors.%s.%s.%s' % (type.lower(), target.lower(), class_name)
            cls = loader.import_class(class_path)

        return cls

    def flush(self, clients=None):
        """
        Object flush method.  Since the object is what has the bins, it should be responsible for managing them.

        :param clients: List of Strings (names of the bins to flush.
        :return: Dict Flush contents for each named bin.  Structure of each is determined by the bin itself.
        """
        results = {}

        if clients:  # Flush the bins requested.
            if len(clients) != 1:
                for name in clients:
                    if name in self.clients:
                        results[name] = self.clients[name].flush()
            else:
                results = self.clients[clients[0]].flush()
        else:  # Flush all the bins for the object
            for name, client in self.clients.items():
                results[name] = client.flush()

        return results
