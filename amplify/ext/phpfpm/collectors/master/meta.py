# -*- coding: utf-8 -*-
from amplify.agent.common.context import context
from amplify.agent.data.eventd import INFO
from amplify.agent.collectors.abstract import AbstractMetaCollector
from amplify.agent.common.util import subp, host
from amplify.ext.phpfpm.util.ps import LS_CMD, LS_CMD_FREEBSD, LS_PARSER
from amplify.ext.phpfpm.util.version import VERSION_PARSER


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class PHPFPMMetaCollector(AbstractMetaCollector):
    """
    Meta collector.  Collects meta data about master
    """
    short_name = 'phpfpm_meta'

    def __init__(self, **kwargs):
        super(PHPFPMMetaCollector, self).__init__(**kwargs)

        self._bin_path = None  # cache for bin_path discovery
        self._version = None  # cache for version discovery
        self._version_line = None  # "" "" ""

        self.register(
            self.bin_path,
            self.version
        )

    @property
    def default_meta(self):
        meta = {
            'type': self.object.type,
            'root_uuid': context.uuid,
            'local_id': self.object.local_id,
            'name': self.object.name,
            'display_name': self.object.display_name,
            'cmd': self.object.cmd,
            'conf_path': self.object.conf_path,
            'workers': len(self.object.workers),
            'bin_path': None,
            'version': None,
            'version_line': None,
        }

        if not self.in_container:
            meta['pid'] = self.object.pid

        return meta

    def bin_path(self):
        """
        Compute the bin_path as part of meta collection to be more tolerant of
        users that utilize `pm.ondemand`.  bin_path is also not required for
        our regular running logic so it can safely be moved down a level (to
        this collector that runs on a regular async basis).

        This used to live in manager._find_all() but it is impossible to cache
        the value there.
        """
        # only compute if bin_path hasn't been found before
        if self._bin_path is None:
            all_pids = [self.object.pid] + self.object.workers

            last_exception = None

            for pid in all_pids:
                ls_cmd_template = LS_CMD_FREEBSD if host.linux_name() == 'freebsd' else LS_CMD
                ls_cmd = ls_cmd_template % pid

                try:
                    ls, _ = subp.call(ls_cmd)
                    context.log.debug('ls "%s" output: %s' % (ls_cmd, ls))
                except Exception as e:
                    last_exception = e
                else:
                    try:
                        self._bin_path = LS_PARSER(ls[0])
                    except Exception as e:
                        exc_name = e.__class__.__name__
                        context.log.debug(
                            'failed to parse ls result "%s" due to %s' %
                            (ls[0], exc_name)
                        )
                        context.log.debug('additional info:', exc_info=True)

                    last_exception = None  # clear last exception for ls
                    break

            # if we never succeeded...log error
            if last_exception:
                exc_name = last_exception.__class__.__name__

                # this is being kept as an error because it has
                # implications for meta collection success/failure
                context.log.debug(
                    'failed to find php-fpm bin path, last attempt: '
                    '"%s" failed due to %s' %
                    (ls_cmd, exc_name)
                )
                context.log.debug('additional info:', exc_info=True)

                # If there is a root_object defined, send an event to the cloud
                if context.objects.root_object:
                    context.objects.root_object.eventd.event(
                        level=INFO,
                        message='php-fpm bin not found'
                    )

        self.meta['bin_path'] = self._bin_path

    def version(self):
        # only compute if version hasn't been found before and we have found a
        # bin_path
        if self._version is None and self._bin_path is not None:
            version, raw_line = VERSION_PARSER(self._bin_path)

            self._version, self._version_line = version, raw_line

        self.meta['version'] = self._version
        self.meta['version_line'] = self._version_line
