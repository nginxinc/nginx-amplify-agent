# -*- coding: utf-8 -*-


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class CommonDataClient(object):
    def __init__(self, object=None):
        self.object = object
        self.current = {}
        self.delivery = {}
