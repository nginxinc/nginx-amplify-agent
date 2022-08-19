# -*- coding: utf-8 -*-
from amplify.agent.common.util.system import get_root_definition
from amplify.agent.managers.abstract import ObjectManager
from amplify.agent.objects.system.object import SystemObject, ContainerSystemObject


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


SYSTEM_OBJECT_MAP = {
    'system': SystemObject,
    'container': ContainerSystemObject
}


class SystemManager(ObjectManager):
    """
    Manager for system objects
    Typically we have only one object since we run in a single system
    """
    name = 'system_manager'
    type = 'system'
    types = ('system', 'container')

    def _discover_objects(self):
        if not self.objects.find_all(types=self.types):
            data = get_root_definition()

            sys_object = SYSTEM_OBJECT_MAP[data['type']](data=data)

            self.objects.register(sys_object)
