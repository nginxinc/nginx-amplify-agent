# -*- coding: utf-8 -*-
"""
heap.py

This is a debugging module that is not used during regular agent usage.  In
fact, it requires the `objgraph` library that is not part of the standard agent
dependencies.  Primarily used in development, you must install the `objgraph`
package before using::

    $ pip install objgraph
"""
import sys
import contextlib
import objgraph

from cStringIO import StringIO

from amplify.agent.common.context import context


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


@contextlib.contextmanager
def capture():
    """
    Sort of a 2.7 hack as described here:

    http://stackoverflow.com/questions/5136611/capture-stdout-from-a-script-in-python

    Python3 has better facilities:

    https://docs.python.org/3.5/library/contextlib.html

    Usage::
        output = None
        with capture() as out:
            print "hi"

            output = out
        print output  # ['hi\n', '']

    Modifying yield from a finally block is really odd and results in wierd behavior.  This is being left as is since
    this really is a Python2 hack.
    """
    default_out, default_err = sys.stdout, sys.stderr
    try:
        out = [StringIO(), StringIO()]
        sys.stdout, sys.stderr = out
        yield out
    finally:
        # alter the yield nicely for string processing
        out[0] = out[0].getvalue()
        out[1] = out[1].getvalue()

        # close the streams
        sys.stdout.close()
        sys.stderr.close()

        # restore the sys streams
        sys.stdout, sys.stderr = default_out, default_err


def heap_logger(block, title=None, out=None):
    """
    Util for logging heap data.

    :param block: String Output data
    :param title: String Title to put above output
    :param out: IOFile Output target (has to follow .write API)
    """

    if out is None:
        if title:
            context.log.debug('[%s]' % title)
        context.log.debug(block)
    else:
        if title:
            out.write('[%s]\n' % title)
        out.write(block)


def show_growth(*args, **kwargs):
    """
    Wrapper around objgraph show_growth that just returns the stdout.
    """
    output = None
    with capture() as out:
        objgraph.show_growth(*args, **kwargs)
        output = out
    return output[0]
