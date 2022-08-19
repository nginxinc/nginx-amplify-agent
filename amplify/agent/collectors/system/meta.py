# -*- coding: utf-8 -*-
import netifaces
import re

import netaddr
import psutil

from amplify.agent.common.context import context
from amplify.agent.common.errors import AmplifySubprocessError
from amplify.agent.common.util import subp
from amplify.agent.common.util.ec2 import AmazonEC2
from amplify.agent.common.util.host import os_name, etc_release, alive_interfaces
from amplify.agent.collectors.abstract import AbstractMetaCollector


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class SystemMetaCollector(AbstractMetaCollector):
    """
    Collects metadata about the system the agent is running on.
    """
    short_name = 'sys_meta'
    proc_cpuinfo_re = re.compile('([\w\.\s]+):\s*(.+)')
    lscpu_re = re.compile('([\w\d\s\(\)\.]+):\s+([\w\d].*)')

    def __init__(self, **kwargs):
        super(SystemMetaCollector, self).__init__(**kwargs)
        self.uuid = self.object.data['uuid']
        self.register(
            self.disk_partitions,
            self.etc_release,
            self.proc_cpuinfo,
            self.lscpu,
            self.uname,
            self.network
        )
        if not self.in_container:
            self.ec2_metadata = AmazonEC2.read_meta()

    @property
    def default_meta(self):
        meta = {
            'type': self.object.type,
            'uuid': self.uuid,
            'os-type': os_name(),
            'display_name': self.object.display_name,
            'tags': context.tags,
            'network': {'interfaces': [], 'default': None},
            'disk_partitions': [],
            'release': {'name': None, 'version_id': None, 'version': None},
            'processor': {'cache': {}}
        }
        if not self.in_container:
            meta['hostname'] = self.object.hostname
            meta['boot'] = int(psutil.boot_time()) * 1000
            meta['ec2'] = self.ec2_metadata or None
        else:
            meta['imagename'] = self.object.imagename
            meta['container_type'] = context.container_type or 'None'

        return meta

    def disk_partitions(self):
        """ disk partitions """
        self.meta['disk_partitions'] = [
            {'mountpoint': x.mountpoint, 'device': x.device, 'fstype': x.fstype}
            for x in psutil.disk_partitions(all=False)
        ]

    def etc_release(self):
        self.meta['release'].update(etc_release())

    def proc_cpuinfo(self):
        """ cat /proc/cpuinfo """
        proc_cpuinfo_out, _ = subp.call('cat /proc/cpuinfo')
        for line in proc_cpuinfo_out:
            kv = re.match(self.proc_cpuinfo_re, line)
            if kv:
                key, value = kv.group(1), kv.group(2)
                if key.startswith('model name'):
                    self.meta['processor']['model'] = value
                elif key.startswith('cpu cores'):
                    self.meta['processor']['cores'] = value

    def lscpu(self):
        """ lscpu """
        lscpu_out, _ = subp.call('lscpu')
        for line in lscpu_out:
            kv = re.match(self.lscpu_re, line)
            if kv:
                key, value = kv.group(1), kv.group(2)
                if key == 'Architecture':
                    self.meta['processor']['architecture'] = value
                elif key == 'CPU MHz':
                    self.meta['processor']['mhz'] = value
                elif key == 'Hypervisor vendor':
                    self.meta['processor']['hypervisor'] = value
                elif key == 'Virtualization type':
                    self.meta['processor']['virtualization'] = value
                elif key == 'CPU(s)':
                    self.meta['processor']['cpus'] = value
                elif 'cache' in key:
                    key = key.replace(' cache', '')
                    self.meta['processor']['cache'][key] = value

    def uname(self):
        """ Collects the full uname for the OS """
        uname_cmd = 'uname -a' if not self.in_container else 'uname -s -r -v -m -p'
        uname_out, _ = subp.call(uname_cmd)
        self.meta['uname'] = uname_out.pop(0)

    def network(self):
        """ network """
        # collect info for all the alive interfaces
        for interface in alive_interfaces():
            addresses = netifaces.ifaddresses(interface)
            interface_info = {'name': interface}

            # collect addresses (if not running in a container)
            if not self.in_container:
                for proto, key in (('ipv4', netifaces.AF_INET), ('ipv6', netifaces.AF_INET6)):
                    protocol_data = addresses.get(key, [{}])[0]
                    if protocol_data:
                        interface_info[proto] = {
                            'address': protocol_data.get('addr').split('%').pop(0),
                            'netmask': protocol_data.get('netmask')
                        }
                        try:
                            address = '%(address)s/%(netmask)s' % interface_info[proto]
                            interface_info[proto]['prefixlen'] = netaddr.IPNetwork(address).prefixlen
                        except:
                            interface_info[proto]['prefixlen'] = None

            # collect MAC address
            interface_info['mac'] = addresses.get(netifaces.AF_LINK, [{}])[0].get('addr')

            self.meta['network']['interfaces'].append(interface_info)

        # get default interface name
        netstat_out, _ = subp.call("netstat -nr | egrep -i '^0.0.0.0|default'", check=False)
        if netstat_out and netstat_out[0]:
            first_matched_line = netstat_out[0]
            default_interface = first_matched_line.split(' ')[-1]
        elif self.meta['network']['interfaces']:
            default_interface = self.meta['network']['interfaces'][0]['name']
        else:
            default_interface = None

        self.meta['network']['default'] = default_interface


class GenericLinuxSystemMetaCollector(SystemMetaCollector):
    pass


class DebianSystemMetaCollector(SystemMetaCollector):
    pass


class CentosSystemMetaCollector(SystemMetaCollector):
    etc_release_re = re.compile(r'^(.+?)\s+(\w+)\s+([\d\.]+)\s+([\w\(\)]+)')

    def etc_release(self):
        """
        Centos6 has different *-release format.
        For example: CentOS release 6.7 (Final)
        """
        super(CentosSystemMetaCollector, self).etc_release()

        if self.meta['release']['version_id'] is None and self.meta['release']['version'] is None:
            try:
                etc_release_out, _ = subp.call('cat /etc/centos-release', check=True)
            except AmplifySubprocessError:
                etc_release_out, _ = subp.call('cat /etc/redhat-release', check=True)

            for line in etc_release_out:
                r = re.match(self.etc_release_re, line)
                if r:
                    self.meta['release']['name'] = r.group(1)
                    self.meta['release']['version_id'] = r.group(3)
                    self.meta['release']['version'] = '%s %s' % (r.group(3), r.group(4))


class GentooSystemMetaCollector(SystemMetaCollector):
    pass


class FreebsdSystemMetaCollector(SystemMetaCollector):

    def etc_release(self):
        """
        FreeBSD has no *-release files. This uses uname -sr instead.
        """
        uname_out, _ = subp.call('uname -sr')
        name, version = uname_out[0].split(' ', 1)
        self.meta['release']['name'] = name
        self.meta['release']['version'] = version
        self.meta['release']['version_id'] = version

    def proc_cpuinfo(self):
        """ cat /proc/cpuinfo """
        self.meta['processor']['cpus'] = psutil.cpu_count(logical=False)
        self.meta['processor']['cores'] = psutil.cpu_count()
        proc_cpuinfo_out, _ = subp.call('sysctl hw.model')
        for line in proc_cpuinfo_out:
            kv = re.match(self.proc_cpuinfo_re, line)
            if kv:
                key, value = kv.group(1), kv.group(2)
                if key.startswith('hw.model'):
                    self.meta['processor']['model'] = value

    def lscpu(self):
        """ lscpu """
        lscpu_out, _ = subp.call('sysctl hw.machine_arch hw.clockrate')
        for line in lscpu_out:
            kv = re.match(self.lscpu_re, line)
            if kv:
                key, value = kv.group(1), kv.group(2)
                if key == 'hw.machine_arch':
                    self.meta['processor']['architecture'] = value
                elif key == 'hw.clockrate':
                    self.meta['processor']['mhz'] = value
