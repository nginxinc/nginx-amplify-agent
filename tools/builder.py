#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
from argparse import ArgumentParser

from builders import deb, rpm
from builders.util import shell_call

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


parser = ArgumentParser(
    description='A tool to build packages for naas-agent with optional revision increment.',
    allow_abbrev=False
)

parser.add_argument(
    '--bumprevision',
    action='store_true',
    default=False,
    help='Increment package revision automatically (by default, just build current one)'
)

if __name__ == '__main__':
    args = parser.parse_args()

    if os.path.isfile('/etc/debian_version'):
        deb.build(bumprevision=args.bumprevision)
    elif os.path.isfile('/etc/redhat-release'):
        rpm.build(bumprevision=args.bumprevision)
    else:
        os_release = shell_call('cat /etc/os-release', important=False)

        if 'amazon linux' in os_release.lower():
            rpm.build(bumprevision=args.bumprevision)
        else:
            print("sorry, it will be done later\n")
