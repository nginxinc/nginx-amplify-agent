# -*- coding: utf-8 -*-
# Some elements of this module use the flup library and are based off of some
# modifications by Vladimir Rusinov (code referenced at
# https://gist.github.com/wofeiwo/3720207).  The copyright notice(s) thereof
# are included below.
#
# Copyright (c) 2006 Allan Saddi <allan@saddi.com>
# Copyright (c) 2011 Vladimir Rusinov <vladimir@greenmice.info>
# Copyright (c) 2016 Grant Hulegaard <grant.hulegaard@nginx.com>
# Copyright (c) 2016 Nginx, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
#
#
import socket

from flup.client.fcgi_app import FCGIApp as FCGIApp_orig
from flup.client.fcgi_app import (
    Record, FCGI_BEGIN_REQUEST, struct, FCGI_BeginRequestBody, FCGI_RESPONDER,
    FCGI_BeginRequestBody_LEN, FCGI_STDIN, FCGI_DATA, FCGI_STDOUT, FCGI_STDERR,
    FCGI_END_REQUEST
)

from amplify.agent.common.util.timeout import timeout


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class FCGIApp(FCGIApp_orig):
    """
    Slightly customized FCGIApp in order to facilitate one of calls through
    FCGI sockets.  Remove/simplify some of the flup feature set surrounding app
    serving to create a usable FCGI client.
    """

    _environPrefixes = [
        'SERVER_', 'HTTP_', 'REQUEST_', 'REMOTE_', 'PATH_', 'CONTENT_',
        'DOCUMENT_', 'SCRIPT_'
    ]

    def __init__(self, connect=None, host=None, port=None, filterEnviron=True):
        if host is not None:
            assert port is not None
            connect = (host, port)

        self._connect = connect
        self._filterEnviron = filterEnviron

    @timeout(60)
    def __call__(self, environ, start_response):
        # For sanity's sake, we don't care about FCGI_MPXS_CONN
        # (connection multiplexing). For every request, we obtain a new
        # transport socket, perform the request, then discard the socket.
        # This is, I believe, how mod_fastcgi does things...

        sock = self._getConnection()

        # Since this is going to be the only request on this connection,
        # set the request ID to 1.
        requestId = 1

        # Begin the request
        rec = Record(FCGI_BEGIN_REQUEST, requestId)
        rec.contentData = struct.pack(FCGI_BeginRequestBody, FCGI_RESPONDER, 0)
        rec.contentLength = FCGI_BeginRequestBody_LEN
        rec.write(sock)

        # Filter WSGI environ and send it as FCGI_PARAMS
        if self._filterEnviron:
            params = self._defaultFilterEnviron(environ)
        else:
            params = self._lightFilterEnviron(environ)
        # TODO: Anything not from environ that needs to be sent also?
        self._fcgiParams(sock, requestId, params)
        self._fcgiParams(sock, requestId, {})

        # Transfer wsgi.input to FCGI_STDIN
        # content_length = int(environ.get('CONTENT_LENGTH') or 0)
        s = ''
        while True:
            # chunk_size = min(content_length, 4096)
            # s = environ['wsgi.input'].read(chunk_size)
            # content_length -= len(s)
            rec = Record(FCGI_STDIN, requestId)
            rec.contentData = s
            rec.contentLength = len(s)
            rec.write(sock)

            if not s:
                break

        # Empty FCGI_DATA stream
        rec = Record(FCGI_DATA, requestId)
        rec.write(sock)

        # Main loop. Process FCGI_STDOUT, FCGI_STDERR, FCGI_END_REQUEST
        # records from the application.
        result = []
        err = ''
        while True:
            inrec = Record()
            inrec.read(sock)
            if inrec.type == FCGI_STDOUT:
                if inrec.contentData:
                    result.append(inrec.contentData.decode('utf-8'))
                else:
                    # TODO: Should probably be pedantic and no longer
                    # accept FCGI_STDOUT records?
                    pass
            elif inrec.type == FCGI_STDERR:
                # Simply forward to wsgi.errors
                err += inrec.contentData
                # environ['wsgi.errors'].write(inrec.contentData)
            elif inrec.type == FCGI_END_REQUEST:
                # TODO: Process appStatus/protocolStatus fields?
                break

        # Done with this transport socket, close it. (FCGI_KEEP_CONN was not
        # set in the FCGI_BEGIN_REQUEST record we sent above. So the
        # application is expected to do the same.)
        sock.close()

        result = ''.join(result)

        # Parse response headers from FCGI_STDOUT
        status = '200 OK'
        headers = []
        pos = 0
        while True:
            eolpos = result.find('\n', pos)
            if eolpos < 0:
                break
            line = result[pos:eolpos - 1]
            pos = eolpos + 1

            # strip in case of CR. NB: This will also strip other
            # whitespace...
            line = line.strip()

            # Empty line signifies end of headers
            if not line:
                break

            # TODO: Better error handling
            header, value = line.split(':', 1)
            header = header.strip().lower()
            value = value.strip()

            if header == 'status':
                # Special handling of Status header
                status = value
                if status.find(' ') < 0:
                    # Append a dummy reason phrase if one was not provided
                    status += ' FCGIApp'
            else:
                headers.append((header, value))

        result = result[pos:]

        # Set WSGI status, headers, and return result.
        # start_response(status, headers)
        # return [result]
        return status, headers, result, err

    def _getConnection(self):
        if self._connect is not None:
            # The simple case. Create a socket and connect to the
            # application.
            if type(self._connect) is str:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            sock.connect(self._connect)

            return sock

        # To be done when I have more time...
        raise NotImplementedError(
            'Launching and managing FastCGI programs not yet implemented'
        )
