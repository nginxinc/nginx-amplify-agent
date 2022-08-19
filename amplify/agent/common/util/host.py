# -*- coding: utf-8 -*-
import netifaces
import os
import platform
import re
import socket
import sys
import uuid as python_uuid
import psutil
import glob

from amplify.agent.common.util import subp
from amplify.agent.common.errors import AmplifySubprocessError
from amplify.agent.common.context import context
from amplify.agent.common.util.ec2 import AmazonEC2


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


VALID_HOSTNAME_RFC_1123_PATTERN = re.compile(
    r"^(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$")

VALID_SRV_RFC_2782_PATTERN = re.compile(
    r"^((_{1}[a-zA-Z0-9\-]*[a-zA-Z0-9])\.){2}(([A-Za-z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$")

MAX_HOSTNAME_LEN = 255


def is_valid_hostname(name):
    """
    Validates hostname
    """
    if name.lower() in (
        'localhost',
        'localhost.localdomain',
        'localhost6.localdomain6',
        'ip6-localhost',
    ):
        context.default_log.warning(
            "Hostname: %s is local" % name
        )
        return False
    if len(name) > MAX_HOSTNAME_LEN:
        context.default_log.warning(
            "Hostname: %s is too long (max length is  %s characters)" %
            (name, MAX_HOSTNAME_LEN)
        )
        return False
    if VALID_HOSTNAME_RFC_1123_PATTERN.match(name) is None and \
            VALID_SRV_RFC_2782_PATTERN.match(name) is None:
        context.default_log.warning(
            "Hostname: %s is not complying with RFC 1123 or RFC 2782" % name
        )
        return False
    return True


def hostname():
    """
    Get the hostname from
    - config
    - unix internals
    - ec2
    """
    result = None

    config = context.app_config
    hostname_from_config = config['credentials']['hostname']
    if hostname_from_config and is_valid_hostname(hostname_from_config):
        result = hostname_from_config

    # then move on to os-specific detection
    if result is None:
        def _get_hostname_unix():
            try:
                # fqdn
                out, err = subp.call('/bin/hostname -f')
                return out[0]
            except Exception:
                return None

        if os_name() in ['mac', 'freebsd', 'linux', 'solaris']:
            unix_hostname = _get_hostname_unix()
            if unix_hostname and is_valid_hostname(unix_hostname):
                result = unix_hostname

    # if its ec2 default hostname, try to get instance_id
    if result is not None and True in [result.lower().startswith(p) for p in [u'ip-', u'domu']]:
        instance_id = AmazonEC2.instance_id()
        if instance_id:
            result = instance_id

    # fall back on socket.gethostname()
    if result is None:
        try:
            socket_hostname = socket.gethostname()
        except socket.error:
            socket_hostname = None
        if socket_hostname and is_valid_hostname(socket_hostname):
            result = socket_hostname

    if result is None:
        result = "%s-%s" % (os_name(), uuid())
        context.log.info('Unable to determine hostname, auto-generated one: "%s"' % result)

    return result


def os_name():
    if sys.platform.startswith('darwin'):
        return 'mac'
    elif sys.platform.startswith('linux'):
        return 'linux'
    elif sys.platform.startswith('freebsd'):
        return 'freebsd'
    elif sys.platform.startswith('sunos'):
        return 'solaris'
    else:
        return sys.platform


def etc_release():
    """ /etc/*-release """
    result = {'codename': None, 'id': None, 'name': None, 'version_id': None, 'version': None}
    mapper = {
        'codename': ('VERSION_CODENAME', 'DISTRIB_CODENAME', 'UBUNTU_CODENAME'),
        'id': 'ID',
        'name': ('NAME', 'DISTRIB_ID'),
        'version_id': ('VERSION_ID', 'DISTRIB_RELEASE'),
        'version': ('VERSION', 'DISTRIB_DESCRIPTION')
    }
    for release_file in glob.glob("/etc/*-release"):
        etc_release_out, _ = subp.call('cat %s' % release_file)
        for line in etc_release_out:
            kv = re.match('(\w+)=(.+)', line)
            if kv:
                key, value = kv.group(1), kv.group(2)
                for var_name, release_vars in mapper.items():
                    if key in release_vars:
                        if result[var_name] is None:
                            result[var_name] = value.replace('"', '')

    if result['name'] is None:
        result['name'] = 'unix'
    return result


def linux_name():
    try:
        out, err = subp.call('cat /etc/*-release')
    except AmplifySubprocessError:
        try:
            out, err = subp.call('uname -s')
            return out[0].lower()
        except AmplifySubprocessError:
            return 'unix'

    for line in out:
        if line.startswith('ID='):
            return line[3:].strip('"').lower()

    full_output = '\n'.join(out).lower()
    if 'oracle linux' in full_output:
        return 'rhel'
    elif 'red hat' in full_output:
        return 'rhel'
    elif 'centos' in full_output:
        return 'centos'
    else:
        return 'linux'


def is_deb():
    return os.path.isfile('/etc/debian_version')


def is_rpm():
    return os.path.isfile('/etc/redhat-release')


def is_amazon():
    os_release, _ = subp.call('cat /etc/os-release', check=False)
    for line in os_release:
        if 'amazon linux' in line.lower():
            return True
    return False


def uuid():
    config_uuid = context.app_config['credentials']['uuid']
    result = python_uuid.uuid5(python_uuid.NAMESPACE_DNS, platform.node() + str(python_uuid.getnode())).hex

    if config_uuid and config_uuid != result:
        context.log.warn('generated UUID != UUID from %s, but we will use one from the config file' % context.app_config.filename)
        return config_uuid
    elif not config_uuid:
        context.log.debug('using generated uuid %s' % result)
        return result

    return config_uuid


def block_devices():
    """
    Returns a list of all non-virtual block devices for a host
    :return: [] of str
    """
    result = []

    # using freebsd
    if os_name() == 'freebsd':
        geom_out, _ = subp.call("geom disk list | grep 'Geom name:' | awk '{print $3}'", check=False)
        result = [device for device in geom_out if device]

    # using linux
    elif os.path.exists('/sys/block/'):
        devices = os.listdir('/sys/block/')
        result = [device for device in devices if '/virtual/' not in os.readlink('/sys/block/%s' % device)]

    return result


def alive_interfaces():
    """
    Returns a list of all network interfaces which have UP state
    see ip link show dev eth0
    will always return lo in a list if lo exists
    :return: [] of str
    """
    alive_interfaces = set()
    try:
        for interface_name, interface in psutil.net_if_stats().items():
            if interface.isup:
                alive_interfaces.add(interface_name)
    except:
        # fallback for centos6
        for interface_name in netifaces.interfaces():
            ip_link_out, _ = subp.call("ip link show dev %s" % interface_name, check=False)
            if ip_link_out:
                first_line = ip_link_out[0]
                state_match = re.match('.+state\s+(\w+)\s+.*', first_line)
                if state_match:
                    state = state_match.group(1)
                    if interface_name == 'lo' or state == 'UP':
                        alive_interfaces.add(interface_name)
                    elif state == 'UNKNOWN':
                        # If state is 'UNKNOWN" (e.g. venet with OpenVZ) check to see if 'UP' is in bracket summary
                        bracket_match = re.match('.+<([\w,\,]+)>.+', first_line)
                        bracket = bracket_match.group(0)
                        for value in bracket.split(','):
                            if value == 'UP':
                                alive_interfaces.add(interface_name)
                                break

    return alive_interfaces
