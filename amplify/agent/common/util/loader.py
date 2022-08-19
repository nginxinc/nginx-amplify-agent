# -*- coding: utf-8 -*-

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


def import_class(qualname):
    module_name, class_name = qualname.rsplit('.', 1)
    module = import_module(module_name)
    return getattr(module, class_name)


def import_module(name):
    mod = __import__(name)
    components = name.split('.')
    for comp in components[1:]:
        mod = getattr(mod, comp)
    return mod
