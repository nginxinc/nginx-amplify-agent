# -*- coding: utf-8 -*-
from amplify.agent.common.context import context


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


ROOT_DEFINITION = dict()


def get_root_definition():
    """Helper function for creating/caching root object definition"""

    if ROOT_DEFINITION and context.app_name !='test':
        return ROOT_DEFINITION

    # Constants
    in_container = bool(context.app_config['credentials']['imagename'])

    ROOT_DEFINITION.update(uuid=context.uuid)

    if in_container:
        ROOT_DEFINITION.update(
            imagename=context.app_config['credentials']['imagename'],
            type='container'
        )
    else:
        ROOT_DEFINITION.update(
            hostname=context.hostname,
            type='system'
        )

    return ROOT_DEFINITION
