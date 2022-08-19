# -*- coding: utf-8 -*-


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


def boolean(value):
    """
    Helper function for taking some basic steps to properly converting a "value" into a properly mapped/cast boolean.
    This was originally designed to be used when handling ConfigParser inputs/values that may not be properly cast due
    to older versions (e.g. agent must support Python 2.6).
    """
    # skip some overhead if value is already a boolean
    if isinstance(value, bool):
        return value

    string_map = {
        'true': True,
        'false': False,
        '1': True,
        '0': False
    }

    # if it is a string try to return the string_map value; return False by default (not found)
    if isinstance(value, str):
        return string_map.get(value.lower(), False)

    # otherwise just return the language boolean cast result
    return bool(value)
