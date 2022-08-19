# -*- coding: utf-8 -*-
import hashlib
import json
import os
import time

import rstr
from crossplane.lexer import _iterescape

from amplify.agent.common.context import context
from amplify.agent.common.util import subp
from amplify.agent.common.util.glib import glib
from amplify.agent.common.util.ssl import ssl_analysis
from amplify.agent.objects.nginx.binary import nginx_v
from amplify.agent.objects.nginx.config.parser import NginxConfigParser, get_filesystem_info

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"

ERROR_LOG_LEVELS = (
    'debug',
    'info',
    'notice',
    'warn',
    'error',
    'crit',
    'alert',
    'emerg'
)


def _enquote(arg):
    if not arg or any(char.isspace() for char in _iterescape(arg)):
        return repr(arg).decode('string_escape')
    else:
        return arg


class NginxConfig(object):
    """
    Nginx config representation **for a running NGINX instance**

    Main tasks:
    - find all log formats
    - find all access logs
    - find all error logs
    - find stub_status url
    """

    def __init__(self, filename, binary=None, prefix=None):
        self.filename = filename
        self.binary = binary
        self.prefix = prefix
        self.log_formats = {}
        self.access_logs = {}
        self.error_logs = {}
        self.test_errors = []
        self.tree = {}
        self.files = {}
        self.directories = {}
        self.directory_map = {}
        self.subtree = []
        self.ssl_certificates = {}
        self.parser_ssl_certificates = []
        self.parser_errors = []
        self.stub_status_urls = []
        self.plus_status_external_urls = []
        self.plus_status_internal_urls = []
        self.api_external_urls = []
        self.api_internal_urls = []
        self.parser = None
        self.wait_until = 0

    def _setup_parser(self):
        self.parser = NginxConfigParser(filename=self.filename)

    def _teardown_parser(self):
        self.parser = None

    def full_parse(self, include_ssl_certs=True):
        context.log.debug('parsing full tree of %s' % self.filename)

        # parse raw data
        try:
            self._setup_parser()
            self.parser.parse(include_ssl_certs=include_ssl_certs)
            self._handle_parse()
        except Exception as e:
            context.log.error('failed to parse config at %s (due to %s)' % (self.filename, e.__class__.__name__))
            context.log.debug('additional info:', exc_info=True)
            self._setup_parser()  # Re-init parser to discard partial data (if any)

        # Post-handling
        # try to add logs from nginx -V configure options
        self.add_configured_variable_logs()

        # try to locate and use default logs (PREFIX/logs/*)
        self.add_default_logs()

        # Go through log files and apply exclude rules (log files are added during .__colect_data()
        self._exclude_logs()

        # try to read from each log file to check if it can be parsed
        self._check_logs()

        # dump access log files, access log formats, and error log files to the debug log
        context.log.debug(
            'parsed log formats, access logs, and error logs:' +
            '\nlog formats: ' + json.dumps(self.log_formats, indent=4, sort_keys=True) +
            '\naccess logs: ' + json.dumps(self.access_logs, indent=4, sort_keys=True) +
            '\nerror logs: ' + json.dumps(self.error_logs, indent=4, sort_keys=True)
        )

    def _handle_parse(self):
        self.tree = self.parser.tree
        self.files = self.parser.files
        self.directories = self.parser.directories
        self.directory_map = self.parser.directory_map
        self.subtree = self.parser.simplify()
        self.ssl_certificates = {}  # gets populated in run_ssl_analysis()
        self.parser_ssl_certificates = self.parser.ssl_certificates
        self.parser_errors = self.parser.errors

        # now that we have all the things we need from parser, we can tear it down
        self._teardown_parser()

        # clear url values in the config that can/will be used to find metrics
        # do this now because self._collect_data() will repopulate the lists
        self.stub_status_urls = []
        self.plus_status_external_urls = []
        self.plus_status_internal_urls = []
        self.api_external_urls = []
        self.api_internal_urls = []

        # go through and collect all logical data
        self._collect_data(self.subtree)

    def collect_structure(self, include_ssl_certs=False):
        """
        Goes through all files (light-parsed includes) and collects their mtime

        :param include_ssl_certs: bool - include ssl certs  or not
        :return: {} - dict of files
        """
        # if self.parser is None, set it up
        if self.parser is None:
            self._setup_parser()

        files, directories = self.parser.get_structure(include_ssl_certs=include_ssl_certs)
        context.log.debug('found %s files for %s' % (len(files.keys()), self.filename))
        context.log.debug('found %s directories for %s' % (len(directories.keys()), self.filename))

        # always teardown the parser
        self._teardown_parser()

        return files, directories

    def total_size(self):
        """
        Returns the total size of a config tree
        :return: int size in bytes
        """
        return sum(data['size'] for data in self.files.values())

    def _collect_data(self, block, ctx=None):
        """
        Searches needed data in config's tree

        :param block: list of statement dicts to parse
        :param ctx: dict with context
        """
        ctx = ctx if ctx is not None else {}

        def usable_log_args(args):
            is_disabled = not args or args[0] == 'off'
            uses_variable = any('$' in arg for arg in args if not arg.startswith('if='))
            return not is_disabled and not uses_variable

        for stmt in block:
            directive = stmt['directive']
            args = stmt['args']

            if directive == 'error_log' and usable_log_args(args):
                path = args[0].replace('"', '').replace("'", '')
                # if not syslog, assume it is a file...if not starts with '/' assume relative path
                if not path.startswith('syslog') and not path.startswith('/'):
                    path = os.path.join(self.prefix, path)

                if path not in self.error_logs:
                    if len(args) > 1 and args[1] in ERROR_LOG_LEVELS:
                        self.error_logs[path] = {'log_level': args[1]}
                    else:
                        self.error_logs[path] = {'log_level': 'error'}  # nginx default log level

            elif directive == 'access_log' and usable_log_args(args):
                path = args[0].replace('"', '').replace("'", '')
                # if not syslog, assume it is a file...if not starts with '/' assume relative path
                if not path.startswith('syslog') and not path.startswith('/'):
                    path = os.path.join(self.prefix, path)

                format = args[1] if len(args) > 1 else None
                self.access_logs[path] = {'log_format': format}

            elif directive == 'log_format':
                name, strings = args[0], args[1:]

                # disregard the (optional) escape parameter
                if len(strings) > 1 and strings[0].startswith('escape='):
                    strings.pop(0)

                self.log_formats[name] = ''.join(
                    x.encode('utf-8').decode('unicode_escape') for x in strings
                )

            elif directive == 'server' and 'upstream' not in ctx:
                listens = []
                for inner_stmt in stmt['block']:
                    if inner_stmt['directive'] == 'listen':
                        listens.append(inner_stmt['args'][0])

                if not listens:
                    listens += ['80', '8000']

                ip_port = []
                for listen in listens:
                    try:
                        ip_port.append(self._parse_listen(listen))
                    except:
                        context.log.error('failed to parse bad ipv6 listen directive: %s' % listen)
                        context.log.debug('additional info:', exc_info=True)

                server_ctx = dict(ctx, ip_port=ip_port)
                for inner_stmt in stmt['block']:
                    if inner_stmt['directive'] == 'server_name':
                        server_ctx['server_name'] = inner_stmt['args'][0]
                        break

                for inner_stmt in stmt['block']:
                    if inner_stmt['directive'] == 'listen':
                        server_ctx['server_schema'] = 'https' if 'ssl' in inner_stmt['args'] else 'http'
                        break

                self._collect_data(stmt['block'], ctx=server_ctx)

            elif directive == 'upstream':
                upstream = args[0]
                upstream_ctx = dict(ctx, upstream=upstream)
                self._collect_data(stmt['block'], ctx=upstream_ctx)

            elif directive == 'location':
                location = ' '.join(map(_enquote, args))
                location_ctx = dict(ctx, location=location)
                self._collect_data(stmt['block'], ctx=location_ctx)

            elif directive == 'stub_status' and 'ip_port' in ctx:
                for url in self._status_url(ctx):
                    if url not in self.stub_status_urls:
                        self.stub_status_urls.append(url)

            elif (directive == 'status' or self._is_plus_dashboard(stmt, ctx)) and 'ip_port' in ctx:
                # use different url builders for external and internal urls
                for url in self._status_url(ctx, server_preferred=True):
                    if url not in self.plus_status_external_urls:
                        self.plus_status_external_urls.append(url)

                # for internal (agent) usage local ip address is a better choice,
                # because the external url might not be accessible from a host
                for url in self._status_url(ctx, server_preferred=False):
                    if url not in self.plus_status_internal_urls:
                        self.plus_status_internal_urls.append(url)

            elif directive == 'api' and 'ip_port' in ctx:
                # use different url builders for external and internal urls
                for url in self._status_url(ctx, server_preferred=True):
                    if url not in self.api_external_urls:
                        self.api_external_urls.append(url)

                # for internal (agent) usage local ip address is a better choice,
                # because the external url might not be accessible from a host
                for url in self._status_url(ctx, server_preferred=False):
                    if url not in self.api_internal_urls:
                        self.api_internal_urls.append(url)

            elif 'block' in stmt:
                self._collect_data(stmt['block'], ctx=ctx)

    @staticmethod
    def _is_plus_dashboard(stmt, ctx):
        """
        Now that the `status` directive is deprecated this method is used to determine
        plus dashboard urls. It does so by checking to see if the config follows the
        conventional pattern for including the plus dashboard:
            location = /dashboard.html {
                root /usr/share/nginx/html;
            }
        Obviously this is not perfect, but it's the best we can do now that the `status`
        directive is gone.
        """
        correct_directive = stmt['directive'] == 'root'
        correct_arguments = stmt['args'] == ['/usr/share/nginx/html']
        correct_location = ctx.get('location', '/').endswith('dashboard.html')
        return correct_directive and correct_arguments and correct_location

    @staticmethod
    def _status_url(ctx, server_preferred=False):
        """
        Creates stub/plus status url based on context

        :param ctx: {} of current parsing context
        :param server_preferred: bool - use server_name instead of listen
        :return: [] of urls
        """
        location = ctx.get('location', '/')

        # remove all modifiers
        location_parts = location.split(' ')
        final_location_part = location_parts[-1]

        # generate a random sting that will fit regex location
        if location.startswith('~'):
            try:
                exact_location = rstr.xeger(final_location_part)

                # check that regex location has / and add it
                if not exact_location.startswith('/'):
                    exact_location = '/%s' % exact_location
            except:
                context.log.debug('bad regex location: %s' % final_location_part)
                exact_location = None
        else:
            exact_location = final_location_part

            # if an exact location doesn't have / that's not a working location, we should not use it
            if not exact_location.startswith('/'):
                context.log.debug('bad exact location: %s' % final_location_part)
                exact_location = None

        if exact_location:
            for ip_port in ctx.get('ip_port'):
                address, port = ip_port
                if server_preferred and 'server_name' in ctx:
                    address = ctx['server_name']

                schema = 'http'
                if 'server_schema' in ctx:
                    schema = ctx['server_schema']

                yield '%s://%s:%s%s' % (schema, address, port, exact_location)

    def run_test(self):
        """
        Tests the configuration using nginx -t
        Saves event info if syntax check was not successful
        """
        start_time = time.time()
        context.log.info('running %s -t -c %s' % (self.binary, self.filename))
        if self.binary:
            try:
                _, nginx_t_err = subp.call("%s -t -c %s" % (self.binary, self.filename), check=False)
                for line in nginx_t_err:
                    if 'syntax is' in line and 'syntax is ok' not in line:
                        self.test_errors.append(line)
            except Exception as e:
                exception_name = e.__class__.__name__
                context.log.error('failed to %s -t -c %s due to %s' % (self.binary, self.filename, exception_name))
                context.log.debug('additional info:', exc_info=True)
        end_time = time.time()
        return end_time - start_time

    def checksum(self):
        """
        Calculates total checksum of all config files, certificates and permissions

        :return: str checksum
        """
        checksums = []
        for file_path, file_data in self.files.items():
            checksums.append(hashlib.sha256(open(file_path, 'rb').read()).hexdigest())
            checksums.append(file_data['permissions'])
            checksums.append(str(file_data['mtime']))
        for dir_data in self.directories.values():
            checksums.append(dir_data['permissions'])
            checksums.append(str(dir_data['mtime']))
        for cert in self.ssl_certificates.keys():
            checksums.append(hashlib.sha256(open(cert, 'rb').read()).hexdigest())
        return hashlib.sha256('.'.join(checksums).encode('utf-8')).hexdigest()

    def _parse_listen(self, listen):
        """
        Parses listen directive value and return ip:port string, like *:80 and so on

        :param listen: str raw listen
        :return: str ip:port
        """
        if '[' in listen:
            # ipv6
            parts = list(filter(len, listen.rsplit(']', 1)))
            address = '%s]' % parts[0]
            port = '80' if len(parts) == 1 else parts[1].split(':')[1]
        else:
            # ipv4
            parts = list(filter(len, listen.rsplit(':', 1)))
            if len(parts) == 1 and parts[0].isdigit():
                address, port = '*', parts[0]
            elif len(parts) == 1:
                address, port = parts[0], '80'
            else:
                address, port = parts

        # standardize address
        if address in ('*', '0.0.0.0'):
            address = '127.0.0.1'
        elif address == '[::]':
            address = '[::1]'

        return address, port

    def add_configured_variable_logs(self):
        """
        Get logs configured through nginx -V options and try to find access and error logs
        This happens only if nginx access and error logs are not configured in nginx.conf
        """
        if self.binary is not None and (len(self.access_logs) < 1 or len(self.error_logs) < 1):
            try:
                v_options = nginx_v(self.binary)
                configure = v_options['configure']
                # adding access or error logs from options only if they are empty
                if len(self.access_logs) < 1:
                    access_log_path = configure.get('http-log-path')
                    if os.path.isfile(access_log_path) and access_log_path is not None:
                        self.access_logs[access_log_path] = {'log_format': None}
                if len(self.error_logs) < 1:
                    error_log_path = configure.get('error-log-path')
                    if os.path.isfile(error_log_path) and error_log_path is not None:
                        self.error_logs[error_log_path] = {'log_level': 'error'}
            except Exception as e:
                exception_name = e.__class__.__name__
                context.log.error(
                    'failed to get configured variables from %s -V due to %s' % (self.binary, exception_name))
                context.log.debug('additional info:', exc_info=True)

    def add_default_logs(self):
        """
        By default nginx uses logs placed in --prefix/logs/ directory
        This method tries to find and add them
        """
        access_log_path = '%s/logs/access.log' % self.prefix
        if os.path.isfile(access_log_path) and access_log_path not in self.access_logs:
            self.access_logs[access_log_path] = {'log_format': None}

        error_log_path = '%s/logs/error.log' % self.prefix
        if os.path.isfile(error_log_path) and error_log_path not in self.error_logs:
            self.error_logs[error_log_path] = {'log_level': 'error'}

    def run_ssl_analysis(self):
        """
        Iterate over a list of ssl_certificate definitions and run ssl_analysis to construct a dictionary with
        ssl_certificate value paired with results fo ssl_analysis.

        :return: float run time
        """
        if not self.parser_ssl_certificates:
            return

        start_time = time.time()

        for cert_filename in set(self.parser_ssl_certificates):
            ssl_analysis_result = ssl_analysis(cert_filename)
            if ssl_analysis_result:
                self.ssl_certificates[cert_filename] = ssl_analysis_result

        end_time = time.time()
        return end_time - start_time

    def _exclude_logs(self):
        """
        Iterate through log file stores and remove ones that match exclude rules.
        """
        # Take comma-separated string of pathname patterns and separate them into individual patterns
        exclude_rules = context.app_config.get('nginx', {}).get('exclude_logs', '').split(',')

        for rule in [x for x in exclude_rules if x]:  # skip potentially empty rules due to improper formatting
            # access logs
            for excluded_file in glib(self.access_logs.keys(), rule):
                del self.access_logs[excluded_file]

            # error logs
            for excluded_file in glib(self.error_logs.keys(), rule):
                del self.error_logs[excluded_file]

    def _check_logs(self):
        """
        Iterate through log file stores and add permissions and if it is readable to the log data
        """
        for logs in (self.access_logs, self.error_logs):
            for log_name in filter(lambda name: not name.startswith('syslog'), logs):

                info = get_filesystem_info(log_name)
                logs[log_name]['permissions'] = info['permissions']

                try:
                    with open(log_name, 'r'):
                        pass
                except:
                    logs[log_name]['readable'] = False
                else:
                    logs[log_name]['readable'] = True
