# -*- coding: utf-8 -*-
import re

from amplify.agent.common.context import context
from amplify.agent.common.util.text import (
    decompose_format, parse_line_split
)


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


REQUEST_RE = re.compile(r'(?P<request_method>[A-Z]+) (?P<request_uri>/.*) (?P<server_protocol>.+)')


class NginxAccessLogParser(object):
    """
    Nginx access log parser
    """
    combined_format = '$remote_addr - $remote_user [$time_local] "$request" ' + \
                      '$status $body_bytes_sent "$http_referer" "$http_user_agent"'

    default_variable = ['.+', str]

    common_variables = {
        'request': ['.+', str],
        'body_bytes_sent': ['\d+', int],
        'bytes_sent': ['\d+', int],
        'connection': ['[\d\s]+', str],
        'connection_requests': ['\d+', int],
        'msec': ['.+', float],
        'pipe': ['[p|\.]', str],
        'request_length': ['\d+', int],
        'request_time': ['.+', str],
        'status': ['\d+', str],
        'server_name': ['.*', str],
        'time_iso8601': ['.+', str],
        'time_local': ['.+', str],
        'upstream_response_time': ['.+', str],
        'upstream_response_length': ['.+', int],
        'upstream_connect_time': ['.+', str],
        'upstream_header_time': ['.+', str],
        'upstream_status': ['.+', str],
        'upstream_cache_status': ['.+', str],
        'gzip_ratio': ['.+', float],
    }

    # TODO: Remove this now semi-unnecessary variable.
    request_variables = {
        'request_method': ['[A-Z]+', str],
        'request_uri': ['/.*', str],
        'server_protocol': ['[\d\.]+', str],
    }

    comma_separated_keys = [
        'upstream_addr',
        'upstream_status'
    ]

    def __init__(self, raw_format=None):
        """
        Takes raw format and generates regex
        :param raw_format: raw log format
        """
        self.raw_format = self.combined_format if raw_format is None \
            else raw_format

        self.keys, self.trie, self.non_key_patterns, self.first_value_is_key = \
            decompose_format(self.raw_format, full=True)

    def parse(self, line):
        """
        Parses the line and if there are some special fields - parse them too
        For example we can get HTTP method and HTTP version from request

        The difference between this and above is that this one uses split
        mechanic rather than trie matching direclty.

        :param line: log line
        :return: dict with parsed info
        """
        result = {'malformed': False}

        # parse the line
        parsed = parse_line_split(
            line,
            keys=self.keys,
            non_key_patterns=self.non_key_patterns,
            first_value_is_key=self.first_value_is_key
        )

        if parsed:
            for key in self.keys:
                # key local vars
                time_var = False

                func = self.common_variables[key][1] \
                    if key in self.common_variables \
                    else self.default_variable[1]

                try:
                    value = func(parsed[key])
                # for example gzip ratio can be '-' and float
                except ValueError:  # couldn't cast log value
                    value = 0
                except KeyError:  # something went wrong with line parsing
                    context.default_log.warn(
                        'failed to find expected log variable "%s" in access '
                        'log line, skipping' % key
                    )
                    context.default_log.debug('additional info:')
                    context.default_log.debug(
                        'keys: %s\nformat: "%s"\nline:"%s"' % (
                            self.keys,
                            self.raw_format,
                            line
                        )
                    )

                # time variables should be parsed to array of float
                if key.endswith('_time'):
                    time_var = True
                    # skip empty vars
                    if value not in ('', '-'):
                        array_value = []
                        for x in value.replace(' ', '').split(','):
                            x = float(x)
                            # workaround for an old nginx bug with time. ask lonerr@ for details
                            if x > 10000000:
                                continue
                            else:
                                array_value.append(x)
                        if array_value:
                            result[key] = array_value

                # Handle comma separated keys
                if key in self.comma_separated_keys:
                    if ',' in value:
                        list_value = value.replace(' ', '').split(',')  # remove spaces and split values into list
                        result[key] = list_value
                    else:
                        result[key] = [value]

                if key not in result and not time_var:
                    result[key] = value
        else:
            context.default_log.debug(
                'could not parse line "%s" with format "%s"' % (
                    line, self.raw_format
                )
            )
            return None

        if 'request' in result:
            try:
                method, uri, proto = result['request'].split(' ')
                result['request_method'] = method
                result['request_uri'] = uri
                result['server_protocol'] = proto
            except:
                result['malformed'] = True
                method = ''

            if not result['malformed'] and len(method) < 3:
                result['malformed'] = True

        return result
