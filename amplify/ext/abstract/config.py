# -*- coding: utf-8 -*-
from amplify.agent.common.context import context
from amplify.agent.common.config.abstract import AbstractConfig as BaseConfig

from amplify.ext.abstract import AMPLIFY_EXT_KEY


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


ROOT_CONFIG_PATH = '/'.join(context.app_config.filename.split('/')[:-1])


class AbstractExtConfig(BaseConfig):
    filename = None
    ext = AMPLIFY_EXT_KEY
    write_new = False
    config = dict()
    config_changes = dict()

    def __init__(self, config_file=None):
        # if filename is not specified, make one according to default
        if self.filename is None:
            self.filename = ROOT_CONFIG_PATH + '/agent.%s.conf' % self.ext

        super(AbstractExtConfig, self).__init__(config_file=config_file)

        # apply any overrides if any (only in memory)
        self.apply(self.config_changes)