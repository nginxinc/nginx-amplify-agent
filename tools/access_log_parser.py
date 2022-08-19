#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time

from argparse import ArgumentParser

from builders.util import color_print

# make amplify libs available
script_location = os.path.abspath(os.path.expanduser(__file__))
agent_repo_path = os.path.dirname(os.path.dirname(script_location))
agent_config_file = os.path.join(
    agent_repo_path, 'etc', 'agent.conf.development'
)
sys.path.append(agent_repo_path)

from amplify.agent.objects.nginx.log.access import NginxAccessLogParser

from amplify.agent.pipelines.file import FileTail, OFFSET_CACHE


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


NAAS_FORMAT = '$remote_addr - $remote_user [$time_local] "$request" $status ' \
              '$body_bytes_sent "$http_referer" "$http_user_agent" ' \
              '"$http_x_forwarded_for" "$upstream_addr" ' \
              '"$upstream_response_time" "$upstream_status" ' \
              '$http_x_amplify_id '


def len_file(filename):
    with open(filename) as f:
        for i, _ in enumerate(f):
            pass
    return i


# construct the CLI argparser
parser = ArgumentParser(
    description='A tool for parsing an NGINX access log using NGINX Amplify.'
)

# positional arguments
parser.add_argument(
    'file',
    help='Target file to parse',
    action='store'
)


# optional arguments
parser.add_argument(
    '-p', '--parser',
    help='Indicate which parser you would like to use [current]',
    action='store',
    required=False,
    default='current'
)
parser.add_argument(
    '-f', '--format',
    help='Log format to use during parse (NGINX default format is used if not '
         'specified)',
    action='store',
    required=False,
    default=None
)
group = parser.add_mutually_exclusive_group()
group.add_argument(
    '-l', '--lines',
    help='Number of lines to parse from file',
    action='store',
    required=False
)
group.add_argument(
    '-t', '--tail',
    help='Number of lines to parse from tail of file',
    action='store',
    required=False
)


if __name__ == '__main__':
    args = parser.parse_args()

    # special format handler
    if args.format == 'naas':
        args.format = NAAS_FORMAT

    # setup parser
    if args.parser.lower() == 'current':
        alog_parser = NginxAccessLogParser(raw_format=args.format)
    else:
        color_print('Invalid parser "%s"' % args.parser.lower(), color='red')
        exit(1)

    # setup tail
    total_lines = len_file(args.file)
    if args.tail:
        with open(args.file) as f:
            for i, _ in enumerate(f):
                if i == int(args.tail):
                    OFFSET_CACHE[args.file] = f.tell()
                    break
    else:
        OFFSET_CACHE[args.file] = 0  # force FileTail to start at beginning

    tail = FileTail(args.file)

    # just some meta data
    if not args.tail and not args.lines:
        lines_to_parse = total_lines
        limit = False
    else:
        lines_to_parse = args.tail or args.lines
        limit = True

    # some user messages about options
    rows, columns = os.popen('stty size', 'r').read().split()
    color_print("\n= Parsing =" + "=" * (int(columns)-11), color="yellow")
    color_print("\n\tOptions:", color="yellow")
    color_print("\t  file: %s" % args.file, color="yellow")
    color_print("\t  format: %s" % alog_parser.raw_format, color="yellow")
    color_print("\t  lines: %s" % lines_to_parse, color="yellow")
    if args.parser != 'old':
        color_print("\tUsing %s parser" % args.parser.upper())
    else:
        color_print("\tUsing OLD parser", color="red")

    start_time = time.time()
    for i, line in enumerate(tail):
        alog_parser.parse(line)
        if limit:
            if int(lines_to_parse) == i:
                break
    end_time = time.time()

    color_print("\n= Results =" + "=" * (int(columns)-11))

    parsed = lines_to_parse if lines_to_parse <= total_lines else total_lines
    print "\nparsed %s lines in %s\n" % (parsed, end_time - start_time)
    exit(0)
