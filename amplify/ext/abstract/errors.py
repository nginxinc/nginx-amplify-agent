# -*- coding: utf-8 -*-
from amplify.agent.common.errors import AmplifyException, AmplifyCriticalException


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class AmplifyExtException(AmplifyException):
    description = 'Something really bad happened in an Extension'


class AmplifyExtCriticalException(AmplifyCriticalException):
    description = 'DOOM 3: Hell on Mars'

