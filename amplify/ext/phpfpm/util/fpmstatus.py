# -*- coding: utf-8 -*-
import gevent

from amplify.agent.common.context import context
from amplify.agent.common.util.timeout import TimeoutException

from amplify.ext.phpfpm.util.inet import INET_IPV4
from amplify.ext.phpfpm.util.fcgi import FCGIApp


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class PHPFPMStatus(object):
    """
    Query wrapper around FCGIApp.  Responsible for properly initializing and
    calling FCGIApp with exception handling.
    """
    def __init__(self, path=None, host=None, port=None, url=None):
        self._path = path
        self._host = host
        self._port = port

        self.connection = None
        self._setup_connection()

        self.env = {}
        self._setup_env(url)

    def _setup_connection(self):
        """
        Setup connection information.  IPV4 or Unix file socket.

        Follows a similar pattern from flup.
        """
        if self._host:
            assert self._port
            self.connection = INET_IPV4(self._host, self._port)

        if self.connection is None:
            assert self._path
            self.connection = self._path

    def _setup_env(self, url):
        """
        Setup environment variables to pass though CGI
        """
        self.env = {
            'SCRIPT_FILENAME': url,
            'QUERY_STRING': '',
            'REQUEST_METHOD': 'GET',
            'SCRIPT_NAME': url,
            'REQUEST_URI': url,
            'GATEWAY_INTERFACE': 'CGI/1.1',
            'SERVER_SOFTWARE': 'amplify-agent',
            'REDIRECT_STATUS': '200',
            'CONTENT_TYPE': '',
            'CONTENT_LENGTH': '0',
            # 'DOCUMENT_URI': url,
            'DOCUMENT_ROOT': '/var/www/',
            'SERVER_PROTOCOL': 'HTTP/1.1',
            'REMOTE_ADDR': '127.0.0.1',
            'REMOTE_PORT': '123'
        }

        if isinstance(self.connection, INET_IPV4):
            self.env.update({
                'SERVER_ADDR': self.connection.host,
                'SERVER_PORT': str(self.connection.port),
                'SERVER_NAME': self.connection.host
            })
        elif isinstance(self.connection, str):
            self.env.update({
                'SERVER_ADDR': self.connection,
                'SERVER_NAME': self.connection
            })

    def _connect(self):
        """
        Initialize an FCGIApp wrapper from flup.  Since FCGIApp doesn't open a
        socket until call, we don't need try-except handling.
        """
        # TODO: Should we cache this FCGIApp object?  Only init once instead of
        #       per call?
        if self.connection is not None:
            # if _connect is a string, assume it is a string path for a Unix
            # File sock
            if isinstance(self.connection, str):
                fcgi = FCGIApp(
                    connect=self.connection
                )
            elif isinstance(self.connection, INET_IPV4):
                fcgi = FCGIApp(
                    host=self.connection.host, port=self.connection.port
                )
            else:
                fcgi = FCGIApp(
                    connect=self.connection
                )
                # this is a hail mary that will bubble a NotImplemented error
                # from FCGIApp if flup can't handle it.

            return fcgi

    def get_status(self):
        """
        Now with meta information all setup, attempt to communicate over socket
        and get status page.

        Example return::
            pool:                 www
            process manager:      dynamic
            start time:           07/Dec/2016:00:13:21 +0000
            start since:          0
            accepted conn:        1
            listen queue:         0
            max listen queue:     0
            listen queue len:     0
            idle processes:       0
            active processes:     1
            total processes:      1
            max active processes: 1
            max children reached: 0
            slow requests:        0
        """
        try:
            with gevent.Timeout(10, TimeoutException):
                fcgi = self._connect()
                resp = fcgi(self.env, lambda x, y: None)
        except TimeoutException:
            context.log.error(
                'pool communication at "%s" timed out' %
                self.connection.__str__()
            )  # use .__str__() because of namedtuple
            context.log.debug('additional info:', exc_info=True)
            resp = ('500', [], '', '')
        except:
            context.log.error(
                'failed to communicate with pool at "%s"' %
                self.connection.__str__()
            )  # use .__str__() because of namedtuple
            context.log.debug('additional info:', exc_info=True)
            resp = ('500', [], '', '')

        status, headers, out, err = resp

        if status.startswith('200'):
            return out
        else:
            context.log.debug(
                'non-success returned by fcgi (status: %s)' % status
            )
            context.log.debug(
                'additional info:\n'
                '  status: %s\n'
                '  headers: %s\n'
                '  out: %s\n'
                '  err: %s\n'
                % resp
            )
