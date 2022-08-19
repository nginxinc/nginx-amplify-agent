# -*- coding: utf-8 -*-
import gevent

from amplify.agent.common.context import context

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


def spawn(f, *args, **kwargs):
    thread = gevent.spawn(f, *args, **kwargs)
    context.log.debug('started "%s"' % f)
    return thread
