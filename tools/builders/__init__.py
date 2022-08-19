# -*- coding: utf-8 -*-
import os

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


def shell_call(cmd):
    print('\033[32m%s\033[0m' % cmd)
    os.system(cmd)
