#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import sys
import time

# make amplify libs available
script_location = os.path.abspath(os.path.expanduser(__file__))
agent_repo_path = os.path.dirname(os.path.dirname(script_location))
agent_config_file = os.path.join(agent_repo_path, 'etc', 'agent.conf.development')
sys.path.append(agent_repo_path)

# setup agent config
from amplify.agent.common.context import context
context.setup(app='agent', config_file=agent_config_file)
context.app_config['daemon']['cpu_sleep'] = 0.0

from amplify.agent.objects.nginx.config.config import NginxConfig

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


def parse_args():
    from argparse import ArgumentParser
    parser = ArgumentParser(description='A tool for using the NGINX Amplify config parser')
    parser.add_argument('-c', '--config', metavar='file', required=True, help='path to nginx config file')

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--light', action='store_true', help='light parse (find all files)')
    group.add_argument('--simple', action='store_true', help='print the simplified config')
    group.add_argument('--dirmap', action='store_true', help='print directory and file map')
    group.add_argument('--payload', action='store_true', help='print entire config payload')

    group = parser.add_mutually_exclusive_group()
    group.add_argument('--pretty', action='store_true', help='pretty print json payloads')
    group.add_argument('-q', '--quiet', action='store_true', help='print only elapsed time')

    args = parser.parse_args()

    args.config = os.path.abspath(os.path.expanduser(args.config))
    if not os.path.exists(args.config):
        parser.error('config: No such file or directory')

    return args


def main():
    args = parse_args()

    def dump(heading, *payloads):
        if heading:
            print('\033[32m{} for {}\033[0m'.format(heading, args.config))
        for x in payloads:
            if isinstance(x, dict) and args.pretty:
                print(json.dumps(x, indent=4, sort_keys=True))
            elif isinstance(x, dict):
                print(json.dumps(x, separators=(',', ':'), sort_keys=True))
            else:
                print(json.dumps(x))  # never prettify print lists

    start = time.time()

    cfg = NginxConfig(filename=args.config)
    if args.light:
        structure = cfg.collect_structure(include_ssl_certs=True)
    else:
        cfg.full_parse()

    runtime = time.time() - start

    if args.quiet:
        print('Parsed in %s seconds' % runtime)
        return

    if args.light:
        dump(None, *structure)
    elif args.simple:
        dump(None, cfg.subtree)
    elif args.dirmap:
        dump('Config files', cfg.files)
        dump('Config directories', cfg.directories)
        dump('Config directory map', cfg.directory_map)
        dump('Config errors', cfg.parser_errors)
    elif args.payload:
        cfg.run_ssl_analysis()
        payload = {
            'tree': cfg.tree,
            'directory_map': cfg.directory_map,
            'files': cfg.files,
            'directories': cfg.directories,
            'ssl_certificates': cfg.ssl_certificates,
            'access_logs': cfg.access_logs,
            'error_logs': cfg.error_logs,
            'errors': {
                'parser': len(cfg.parser_errors),
                'test': len(cfg.test_errors)
            }
        }
        dump(None, payload)
    else:
        cfg.run_ssl_analysis()
        dump('Config tree', cfg.tree)
        dump('Config files', cfg.files)
        dump('Config directory map', cfg.directory_map)
        dump('SSL certificates', cfg.ssl_certificates)
        dump(
            'Stub status/plus status/api urls',
            cfg.stub_status_urls,
            cfg.plus_status_external_urls,
            cfg.plus_status_internal_urls,
            cfg.api_external_urls,
            cfg.api_internal_urls
        )
        dump('Access logs', cfg.access_logs)
        dump('Error logs', cfg.error_logs)
        dump('Log formats', cfg.log_formats)
        dump('Config errors', cfg.parser_errors)

    print('\033[32mParsed in %s seconds\033[0m' % runtime)


if __name__ == '__main__':
    main()
