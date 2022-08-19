# -*- coding: utf-8 -*-
from amplify.agent.common.context import context
from amplify.agent.common.util import subp


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


VERSION_CMD = "%s --version"


def VERSION_PARSER(bin_path):
    try:
        raw_stdout, _ = subp.call(VERSION_CMD % bin_path)
    except Exception as e:
        exc_name = e.__class__.__name__
        # this is being logged as debug only since we will rely on bin_path
        # collection error to tip off support as to what is going wrong with
        # version detection
        context.log.debug(
            'failed to get version info from "%s" due to %s' %
            (bin_path, exc_name)
        )
        context.log.debug('additional info:', exc_info=True)
    else:
        # first line is all that we are interested in::
        #   PHP 5.5.9-1ubuntu4.17 (fpm-fcgi) (built: May 19 2016 19:08:26)
        raw_line = raw_stdout[0]

        raw_version = raw_line.split()[1]  # 5.5.9-1ubuntu4.17

        version = []
        for char in raw_version:
            if char.isdigit() or char in ('.', '-'):
                version.append(char)
            else:
                break
        # version = ['5', '.', '5', '.', '9', '-', '1']

        # '5.5.9-1',
        # 'PHP 5.5.9-1ubuntu4.17 (fpm-fcgi) (built: May 19 2016 19:08:26)'
        return ''.join(version), raw_line
