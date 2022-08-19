"""
Helpers for working with sockets.
"""
# -*- coding: utf-8 -*-


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


def ipv4_address(address=None, host='', port='80', full_format=False, silent=False):
    """
    Helper function that splits an ipv4 address and returns host, port combination.

    It also optionally does formatting, so you can go from parts to a properly formatted address.

    Note the intention of this function is to provide a common working medium with which to pass socket information
    around our agent logic.  It's an abstraction layer.  This might be better served as an actual object, but for now
    this works.

    :param address: String Fully qualified ipv4 address; must contain a ':' even if specifying a wildcard.
    :param host: String Qualified ipv4 hostname (either resolvable name or ipv4 IP)
    :param port: String Port number
    :param full_format: Boolean Flag for determining whether or not to send back a string address.
    :param silent: Boolean Flag for indicating whether errors should be raised or not.
    :return: Tuple (String host, String port, (optional) String full_format)
    """
    # if no address, construct one from passed host/port and defaults
    if address is None:
        address = ':'.join((host, port))

    parts = address.rsplit(':', 1)  # TODO: Check to see if this .rsplit() lends itself to working with ipv6 a well

    # make sure we got all of the expected pieces
    if len(parts) < 2:
        if '.' in parts[0] or '*' in parts[0]:
            parts.append(port)
        else:
            parts.insert(0, '')

    # replace empty host with wildcard
    if parts[0] == '':
        parts[0] = '*'

    # sanity check (make sure port is int castable)
    try:
        int(parts[1])  # raises ValueError
    except ValueError as e:
        if not silent:
            raise e

    result = (parts[0], parts[1], ':'.join(parts))

    return result if full_format else result[:2]
