# -*- coding: utf-8 -*-
import time
import cProfile

from amplify.agent.common.context import context


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


def do_cprofile(func):
    """
    Decorator that should be used to create and dump cprofiles of Python logic.  To use, simply wrap the desired
    profile function via '@do_cprofile' and watch logs to see exactly which file it was dumped to in /tmp/.

    Once you have a .dump binary, you can load it and display it with something like:

    @ >>> import pstats
    @ >>> p = pstats.Stats('/tmp/func-111111.dump')
    @ >>> p.sort_stats('cumulative').print_stats(20)
    """
    def profiled_func(*args, **kwargs):
        profile = cProfile.Profile()
        started = int(time.time())
        try:
            profile.enable()
            result = func(*args, **kwargs)
            profile.disable()
            return result
        finally:
            dump_file = '/tmp/%s-%s.dump' % (func.__name__, started)
            context.log.debug('dumped run to %s' % dump_file)
            profile.dump_stats(dump_file)
    return profiled_func
