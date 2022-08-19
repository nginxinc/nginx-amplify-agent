# -*- coding: utf-8 -*-
from amplify.agent import Singleton

from amplify.agent.objects.nginx.config.config import NginxConfig


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class NginxConfigTank(Singleton):
    """
    NginxConfig tank that holds NginxConfig objects for granular tracking and
    management.  Useful for passing NginxConfigs between agent objects.

    TODO: Think about simplifying our NginxConfig address pattern (perhaps just filename)
    """

    def __init__(self):
        self._configs = {}

    def __getitem__(self, ident):
        # if the config does not exist, create it
        filename, prefix, bin_path = ident
        if ident not in self._configs:
            self._configs[ident] = NginxConfig(filename=filename, prefix=prefix, binary=bin_path)

        return self._configs[ident]

    def __delitem__(self, ident):
        del self._configs[ident]

    def __setitem__(self, *args, **kwargs):
        pass  # disable __setitem__

    def __len__(self):
        return len(self._configs)

    def keys(self):
        return self._configs.keys()
