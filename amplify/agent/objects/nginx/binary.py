# -*- coding: utf-8 -*-
import re

from amplify.agent.common.util import subp
from amplify.agent.common.context import context

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"

DEFAULT_PREFIX = '/usr/local/nginx'
DEFAULT_CONFPATH = 'conf/nginx.conf'

_SSL_LIB_CAPTURE_GROUPS = r'(\S+) +(\S+)(?: +(\d{1,2} +\w{3,} +\d{4}))?'
BUILT_WITH_RE = re.compile('^built with ' + _SSL_LIB_CAPTURE_GROUPS)
RUNNING_WITH_RE = re.compile('\(running with ' + _SSL_LIB_CAPTURE_GROUPS + '\)$')
RUN_WITH_RE = re.compile('^run with ' + _SSL_LIB_CAPTURE_GROUPS)


def nginx_v(bin_path):
    """
    call -V and parse results

    :param bin_path str - path to binary
    :return {} - see result
    """
    result = {
        'version': None,
        'plus': {'enabled': False, 'release': None},
        'ssl': {'built': None, 'run': None},
        'configure': {}
    }

    _, nginx_v_err = subp.call("%s -V" % bin_path)
    for line in nginx_v_err:
        # SSL stuff
        try:
            if line.lower().startswith('built with') and 'ssl' in line.lower():
                match = BUILT_WITH_RE.search(line)
                result['ssl']['built'] = list(match.groups())

                # example: "built with OpenSSL 1.0.2g-fips 1 Mar 2016 (running with OpenSSL 1.0.2g 1 Mar 2016)"
                match = RUNNING_WITH_RE.search(line) or match
                result['ssl']['run'] = list(match.groups())

            elif line.lower().startswith('run with') and 'ssl' in line.lower():
                match = RUN_WITH_RE.search(line)
                result['ssl']['run'] = list(match.groups())
        except:
            context.log.error('Failed to determine ssl library from "%s"' % line, exc_info=True)

        parts = line.split(':', 1)
        if len(parts) < 2:
            continue

        # parse version
        key, value = parts
        if key == 'nginx version':
            # parse major version
            major_parsed = re.match('.*/([\d\w\.]+)', value)
            result['version'] = major_parsed.group(1) if major_parsed else value.lstrip()

            # parse plus version
            if 'plus' in value:
                plus_parsed = re.match('.*\(([\w\-]+)\).*', value)
                if plus_parsed:
                    result['plus']['enabled'] = True
                    result['plus']['release'] = plus_parsed.group(1)

        # parse configure
        elif key == 'configure arguments':
            arguments = _parse_arguments(value)
            result['configure'] = arguments

    return result


def get_prefix_and_conf_path(cmd, configure=None):
    """
    Finds prefix and path to config based on running cmd and optional configure args

    :param running_binary_cmd: full cmd from ps
    :param configure: parsed configure args from nginx -V
    :return: prefix, conf_path
    """
    cmd = cmd.replace('nginx: master process ', '')
    params = iter(cmd.split())

    # find bin path
    bin_path = next(params)
    prefix = None
    conf_path = None

    # try to find config and prefix
    for param in params:
        if param == '-c':
            conf_path = next(params, None)
        elif param == '-p':
            prefix = next(params, None)

    # parse nginx -V
    parsed_v = nginx_v(bin_path)
    if configure is None:
        configure = parsed_v['configure']

    # if prefix was not found in cmd - try to read it from configure args
    # if there is no key "prefix" in args, then use default
    if not prefix:
        prefix = configure.get('prefix', DEFAULT_PREFIX)
    if not conf_path:
        # if there is a conf_path get it from the config file
        if context.app_config.get('nginx', {}).get('configfile'):
            conf_path = context.app_config['nginx']['configfile']
            if not conf_path.startswith('/'):
                conf_path = '/' + conf_path
        # else get it from the parsed information/DEFAULT
        else:
            conf_path = configure.get('conf-path', DEFAULT_CONFPATH)

    # remove trailing slashes from prefix
    prefix = prefix.rstrip('/')

    # start processing conf_path
    # if it has not an absolutely path, then we should add prefix to it
    if not conf_path.startswith('/'):
        conf_path = '%s/%s' % (prefix, conf_path)

    return bin_path, prefix, conf_path, parsed_v['version']


def _parse_arguments(argstring):
    """
    Parses argstring from nginx -V

    :param argstring: configure string
    :return: {} of parsed string
    """
    if argstring.startswith('configure arguments:'):
        __, argstring = argstring.split(':', 1)

    arg_parts = iter(filter(len, argstring.split(' --')))
    arguments = {}

    for part in arg_parts:
        # if the argument is a simple switch, add it and move on
        if '=' not in part:
            arguments[part] = True
            continue

        key, value = part.split('=', 1)

        # this fixes quoted argument values that broke from the ' --' split
        if value.startswith("'"):
            while not value.endswith("'"):
                value += ' --' + next(arg_parts)

        # if a key is set multiple times, values are stored as a list
        if key not in arguments:
            arguments[key] = value
        elif not isinstance(arguments[key], list):
            arguments[key] = [arguments[key], value]
        else:
            arguments[key].append(value)

    return arguments
