"""
Asyncore implementation of a syslog interface.  Adapted from "Tiny Syslog Server in Python" (
https://gist.github.com/marcelom/4218010) using Asyncore (https://docs.python.org/2/library/asyncore.html).  Some
inspiration for asyncore implementation derived from pymotw (https://pymotw.com/2/asyncore/).

SyslogTail spawns coroutine which in turns spawns an asyncore implemented syslog server and handler/cache and returns
the received messages when iterated.
"""
# -*- coding: utf-8 -*-
import copy
import asyncore
import socket
from collections import deque

from threading import current_thread
from amplify.agent.common.util.threads import spawn

from amplify.agent.common.context import context
from amplify.agent.common.errors import AmplifyException

from amplify.agent.managers.abstract import AbstractManager
from amplify.agent.pipelines.abstract import Pipeline


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


SYSLOG_ADDRESSES = set()


class AmplifyAddresssAlreadyInUse(AmplifyException):
    description = "Couldn't start socket listener because address already in use"


class SyslogServer(asyncore.dispatcher):
    """Simple socket server that creates a socket and listens for and caches UDP packets"""

    def __init__(self, cache, address, chunk_size=8192):
        # Explicitly passed shared cache object
        self.cache = cache

        # Custom constants
        self.chunk_size = chunk_size

        # Old-style class super
        asyncore.dispatcher.__init__(self)

        # asyncore server init
        self.create_socket(socket.AF_INET, socket.SOCK_DGRAM)  # asyncore socket wrapper
        self.bind(address)  # bind afore wrapped socket to address
        self.address = self.socket.getsockname()  # use socket api to retrieve address (address we actually bound to)
        SYSLOG_ADDRESSES.add(self.address)
        context.log.debug('syslog server binding to %s' % str(self.address))

    def handle_read(self):
        """Called when a read event happens on the socket"""
        data = bytes.decode(self.recv(self.chunk_size).strip())
        try:
            log_record = data.split('amplify: ', 1)[1]  # this implicitly relies on the nginx syslog format specifically
            self.cache.append(log_record)
        except Exception:
            context.log.error('error handling syslog message (address:%s, message:"%s")' % (self.address, data))
            context.log.debug('additional info:', exc_info=True)

    def close(self):
        context.log.debug('syslog server closing')
        asyncore.dispatcher.close(self)


class SyslogListener(AbstractManager):
    """This is just a container to manage the SyslogServer listen/handle loop."""
    name = 'syslog_listener'

    def __init__(self, cache, address, **kwargs):
        super(SyslogListener, self).__init__(**kwargs)
        self.server = SyslogServer(cache, address)

    def start(self):
        current_thread().name = self.name
        context.setup_thread_id()

        self.running = True

        while self.running:
            self._wait(0.1)
            # This means that we don't increment every time a UDP message is handled, but rather every listen "period"
            context.inc_action_id()
            asyncore.loop(timeout=self.interval, count=10)
            # count is arbitrary since timeout is unreliable at breaking asyncore.loop

    def stop(self):
        self.server.close()
        context.teardown_thread_id()
        super(SyslogListener, self).stop()


class SyslogTail(Pipeline):
    """Generalized Pipeline wrapper to provide a developer API for interacting with UDP listener."""
    def __init__(self, address, maxlen=10000, **kwargs):
        super(SyslogTail, self).__init__(name='syslog:%s' % str(address))
        self.kwargs = kwargs  # only have to record this due to new listener fail-over logic
        self.maxlen = maxlen
        self.cache = deque(maxlen=self.maxlen)
        self.address = address  # This stores the address that we were passed
        self.listener = None
        self.listener_setup_attempts = 0
        self.thread = None

        # Try to start listener right away, handle the exception
        try:
            self._setup_listener(**self.kwargs)
        except AmplifyAddresssAlreadyInUse as e:
            context.log.warning(
                'failed to start listener during syslog tail init due to "%s", will try later (attempts: %s)' % (
                    e.__class__.__name__,
                    self.listener_setup_attempts
                )
            )
            context.log.debug('additional info:', exc_info=True)

        self.running = True

    def __iter__(self):
        if not self.listener and self.listener_setup_attempts < 3:
            try:
                self._setup_listener(**self.kwargs)
                context.log.info(
                    'successfully started listener during "SyslogTail.__iter__()" after %s failed attempt(s)' % (
                        self.listener_setup_attempts
                    )
                )
                self.listener_setup_attempts = 0  # reset attempt counter
            except AmplifyAddresssAlreadyInUse as e:
                if self.listener_setup_attempts < 3:
                    context.log.warning(
                        'failed to start listener during "SyslogTail.__iter__()" due to "%s", '
                        'will try again (attempts: %s)' % (
                            e.__class__.__name__,
                            self.listener_setup_attempts
                        )
                    )
                    context.log.debug('additional info:', exc_info=True)
                else:
                    context.log.error(
                        'failed to start listener %s times, will not try again' % self.listener_setup_attempts
                    )
                    context.log.debug('additional info:', exc_info=True)

        current_cache = copy.deepcopy(self.cache)
        context.log.debug('syslog tail returned %s lines captured from %s' % (len(current_cache), self.name))
        self.cache.clear()
        return iter(current_cache)

    def _setup_listener(self, **kwargs):
        if self.address in SYSLOG_ADDRESSES:
            self.listener_setup_attempts += 1
            raise AmplifyAddresssAlreadyInUse(
                message='cannot initialize "%s" because address is already in use' % self.name,
                payload=dict(
                    address=self.address,
                    used=list(SYSLOG_ADDRESSES)
                )
            )

        SYSLOG_ADDRESSES.add(self.address)
        self.listener = SyslogListener(cache=self.cache, address=self.address, **kwargs)
        self.thread = spawn(self.listener.start)

    def stop(self):
        if self.running:
            # Remove from used addresses
            for address in set((self.address, self.listener.server.address)):
                SYSLOG_ADDRESSES.remove(address)

            self.listener.stop()  # Close the UDP server
            self.thread.kill()  # Kill the greenlet

            # Unassign variables to reduce reference count for GC
            self.listener = None
            self.thread = None

            # For good measure clear the cache to free memory and set running variable manually to False
            self.cache.clear()
            self.running = False
            context.log.debug('syslog tail stopped')

    def __del__(self):
        self.stop()
