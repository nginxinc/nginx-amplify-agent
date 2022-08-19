# -*- coding: utf-8 -*-
"""
This helper may be done using psutil_process hooks::

    mem_info = context.psutil_process.memory_info()
    mem_info.rss
    mem_info.vms

All information from .memory_info() returns bytes.
"""
import os

from functools import wraps

from amplify.agent.common.context import context


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


scale = {'kB': 1024.0, 'mB': 1024.0 * 1024.0,
         'KB': 1024.0, 'MB': 1024.0 * 1024.0}


def report():
    # get pseudo file  /proc/<pid>/status
    proc_status = '/proc/%d/status' % os.getpid()
    try:
        t = open(proc_status)
        v = t.read()
        t.close()
    except:
        context.log.error('mem', exc_info=True)
        return 0, 0

    # get VmKey line e.g. 'VmRSS:  9999  kB\n ...'
    results = []
    for vm_key in ['VmSize:', 'VmRSS:']:
        i = v.index(vm_key)
        _ = v[i:].split(None, 3)  # whitespace
        if len(_) < 3:
            results.append(0)  # invalid format?
        # convert Vm value to bytes
        results.append(int(float(_[1]) * scale[_[2]] / 1024))

    return results


def memory_info():
    return context.psutil_process.memory_info()


#
# DEBUG Utils
#


def memory_logger(rss, vms, prefix='', out=None):
    """Just a util for logging into debug memory data"""
    prefix += ' ' if not prefix.endswith(' ') else ''
    message = 'memory stats (rss: %s, vms: %s)' % (rss, vms)

    if out is None:
        context.log.debug('%s%s' % (prefix, message))
    else:
        out.write('%s%s\n' % (prefix, message))


def do_mprofile(func):
    """Wrapper that logs memory before and after a wrapped function call."""
    @wraps(func)
    def decorated_func(*args, **kwargs):
        name = func.__name__ if hasattr(
            func, '__name__') else func.__class__.__name__

        mem_info_before = memory_info()
        memory_logger(mem_info_before.rss, mem_info_before.vms,
                      prefix='[%s] BEFORE' % name)

        result = func(*args, **kwargs)

        mem_info_after = memory_info()
        memory_logger(mem_info_after.rss, mem_info_after.vms,
                      prefix='[%s] AFTER' % name)

        memory_logger(
            mem_info_after.rss - mem_info_before.rss,
            mem_info_after.vms - mem_info_before.vms,
            prefix='[%s] DIFF' % name
        )

        return result
    return decorated_func


class mprofile(object):
    """
    A more robust class style decorator for modestly configurable memory logging.  This primarily allows configuration
    of whether or not to output before and after messages in addition to overall diff one.  By default this verbosity is
    "False" and only diff is logged.

    Since we are storing the result in a transitional state, this memory diff may be misleading since the result of the
    function will be in memory during the log handling.
    """

    def __init__(self, verbose=False, out=None):
        self.verbose = verbose
        self.out = out

    def __call__(self, func):
        decor_self = self

        def decorated_func(*args, **kwargs):
            name = func.__name__ if hasattr(
                func, '__name__') else func.__class__.__name__

            mem_info_before = memory_info()
            if decor_self.verbose:
                memory_logger(
                    mem_info_before.rss, mem_info_before.vms, prefix='[%s] BEFORE' % name, out=decor_self.out
                )

            result = func(*args, **kwargs)

            mem_info_after = memory_info()
            if decor_self.verbose:
                memory_logger(
                    mem_info_after.rss, mem_info_after.vms, prefix='[%s] AFTER' % name, out=decor_self.out
                )

            memory_logger(
                mem_info_after.rss - mem_info_before.rss,
                mem_info_after.vms - mem_info_before.vms,
                prefix='[%s] DIFF' % name,
                out=decor_self.out
            )

            return result

        return decorated_func


class mstatus(object):
    """
    Robust class-style decorator for logging current memory and optionally tracking the previous value in wrapper
    global context.

    This logging is done before calling the wrapped function.
    """
    PREV = None

    def __init__(self, verbose=False, out=False):
        self.verbose = verbose
        self.out = out

    def __call__(self, func):
        decor_self = self

        def decorated_func(*args, **kwargs):
            name = func.__name__ if hasattr(
                func, '__name__') else func.__class__.__name__
            mem_info = memory_info()
            memory_logger(mem_info.rss, mem_info.vms,
                          prefix='[%s] CURRENT' % name, out=decor_self.out)

            if decor_self.verbose and decor_self.PREV:
                memory_logger(
                    mem_info.rss - decor_self.PREV.rss,
                    mem_info.vms - decor_self.PREV.vms,
                    prefix='[%s] CURRENT TREND' % name,
                    out=decor_self.out
                )

            decor_self.PREV = mem_info

            return func(*args, **kwargs)

        return decorated_func


MSTATUS_PREV = None


def do_mstatus(overall=True, verbose=False, out=False):
    """
    Helpful function style calling for mstatus decorator logic above.  This is useful for situations where there is no
    function to wrap but we do want to log an 'mstatus' output.

    CAUTION: Unlike the decorator version, this profiler will be tracked using a GLOBAL style variable.  This means that
    every call will affect the global store/behavior of this func.
    """
    global MSTATUS_PREV  # have to use global since `None` is immutable type
    prev = bool(MSTATUS_PREV is not None)

    mem_info = memory_info()

    if overall:
        memory_logger(
            mem_info.rss,
            mem_info.vms,
            prefix='[GLOBAL] CURRENT',
            out=out
        )

    if verbose and prev:
        rss_diff = mem_info.rss - MSTATUS_PREV.rss
        vms_diff = mem_info.vms - MSTATUS_PREV.vms
        memory_logger(
            rss_diff,
            vms_diff,
            prefix='[GLOBAL] CURRENT TREND',
            out=out
        )

    MSTATUS_PREV = mem_info

    if verbose and prev:
        # return a True/False flag to indicate that there was a memory delta.
        return bool(rss_diff or vms_diff)
    elif verbose:
        return False
