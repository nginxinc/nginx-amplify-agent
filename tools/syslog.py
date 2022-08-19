#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import asyncore
import socket

from optparse import OptionParser, Option
from collections import deque

sys.path.append(os.getcwd())  # to make amplify libs available

from amplify.agent.common.context import context
context.setup(
    app='agent',
    config_file='etc/agent.conf.development',
)

from amplify.agent.pipelines.syslog import SyslogServer


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "grant.hulegaard@nginx.com"


# HELPERS


cache = deque(maxlen=10000)


class UDPClient(asyncore.dispatcher):
    """Sends datagrams to a socket"""

    def __init__(self, address):
        self.counter = 0
        self.template = "This is message #%s"
        asyncore.dispatcher.__init__(self)

        self.create_socket(socket.AF_INET, socket.SOCK_DGRAM)  # asyncore socket wrapper
        self.connect(address)

    def handle_write(self):
        self.counter += 1
        message = self.template % self.counter
        self.send(message)
        context.log.debug('Sent %s' % message)


# SCRIPT

usage = "usage: sudo -u nginx %prog -h"

option_list = (
    Option(
        '-a', '--address',
        action='store',
        dest='address',
        type='string',
        help='socket address',
        default='localhost'
    ),
    Option(
        '-p', '--port',
        action='store',
        dest='port',
        type='int',
        help='socket port',
        default='514'
    ),
)

parser = OptionParser(usage, option_list=option_list)
(options, args) = parser.parse_args()


if __name__ == '__main__':
    address = (options.address, options.port)
    server = SyslogServer(cache, address)
    client = UDPClient(address)

    while True:
        context.log.debug('Main event loop; cache length: %s' % len(cache))
        asyncore.loop(timeout=1, count=100)
