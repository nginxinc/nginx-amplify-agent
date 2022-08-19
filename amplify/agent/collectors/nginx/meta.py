# -*- coding: utf-8 -*-
import re

import psutil
from amplify.agent.collectors.abstract import AbstractMetaCollector

from amplify.agent.common.context import context
from amplify.agent.common.util import subp

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class NginxMetaCollector(AbstractMetaCollector):
    dpkg_s_re = re.compile('([\w\-\.]+)\s*:\s*(.+)')
    dpkg_l_re = re.compile('([\d\w]+)\s+([\d\w\.\-]+)\s+([\d\w\.\-\+~]+)\s')

    short_name = 'nginx_meta'

    def __init__(self, **kwargs):
        super(NginxMetaCollector, self).__init__(**kwargs)
        self.register(
            self.open_ssl,
            self.find_packages
        )
        if not self.in_container:
            self.register(
                self.nginx_uptime
            )

    @property
    def default_meta(self):
        meta = {
            'type': 'nginx',  # Hard coded since only 1 'nginx' object in backend.
            'local_id': self.object.local_id,
            'root_uuid': context.uuid,
            'running': True,
            'display_name': self.object.display_name,
            'stub_status_enabled': self.object.stub_status_enabled,
            'status_module_enabled': self.object.plus_status_enabled,
            'stub_status_url': self.object.stub_status_url,
            'plus_status_url': self.object.plus_status_external_url or self.object.plus_status_internal_url,
            'version': self.object.parsed_v['version'],
            'parent_hostname': context.app_config['credentials']['imagename'] or context.hostname,
            'plus': self.object.parsed_v['plus'],
            'configure': self.object.parsed_v['configure'],
            'packages': {},
            'path': {'bin': self.object.bin_path, 'conf': self.object.conf_path},
            'built_from_source': False,
            'ssl': self.object.parsed_v['ssl']
        }
        if not self.in_container:
            meta['start_time'] = None
            meta['pid'] = self.object.pid
        return meta

    def open_ssl(self):
        """
        Old nginx uses standard openssl library - this method tries to find its version
        """
        if self.meta['ssl']['built'] is None:
            openssl_out, _ = subp.call('openssl version')
            if openssl_out[0]:
                version = openssl_out[0].split()[1]
                self.meta['ssl'] = {
                    'built': ['openssl', version],
                    'run': ['openssl', version]
                }

    def find_packages(self):
        """
        Tries to find a package for the running binary
        """
        package = None

        # find which package contains our binary
        dpkg_s_out, dpkg_s_err = subp.call('dpkg -S %s' % self.object.bin_path, check=False)
        for line in dpkg_s_out:
            kv = re.match(self.dpkg_s_re, line)
            if kv:
                package = kv.group(1)
                break

        if 'no path' in dpkg_s_err[0]:
            self.meta['built_from_source'] = True

        if package:
            # get version
            all_installed_packages = {}
            dpkg_l_out, _ = subp.call("dpkg -l | grep nginx")
            for line in dpkg_l_out:
                gwe = re.match(self.dpkg_l_re, line)
                if gwe:
                    if gwe.group(2).startswith('nginx'):
                        all_installed_packages[gwe.group(2)] = gwe.group(3)

            if package in all_installed_packages:
                self.meta['packages'] = {package: all_installed_packages[package]}

    def nginx_uptime(self):
        """ collect info about start time """
        master_process = psutil.Process(self.object.pid)
        self.meta['start_time'] = int(master_process.create_time()) * 1000


class GenericLinuxNginxMetaCollector(NginxMetaCollector):
    def find_packages(self):
        pass


class DebianNginxMetaCollector(NginxMetaCollector):
    pass


class GentooNginxMetaCollector(NginxMetaCollector):

    def find_packages(self):
        """ Find a package with running binary """

        equery_out, equery_err = subp.call(
            'equery --no-color --no-pipe --quiet belongs --early-out %s' % self.object.bin_path,
            check=False
        )
        if equery_out[0]:
            category, package = equery_out[0].split('/', 1)
            name, version = package.split('-', 1)
            if name == 'nginx':
                self.meta['packages'] = {category + '/nginx': version}

        elif not equery_err[0]:
            self.meta['built_from_source'] = True


class CentosNginxMetaCollector(NginxMetaCollector):

    def find_packages(self):
        """ Find a package with running binary """
        package, version = None, None

        rpm_out, rpm_err = subp.call(
            'rpm -qf %s ' % self.object.bin_path + '--queryformat="%{NAME} %{VERSION}-%{RELEASE}.%{ARCH}\\n"',
            check=False
        )

        # looks like *some* centos/rpm versions will NOT consider
        # 'is not owned by' as an error
        if rpm_out and rpm_out[0]:
            if 'is not owned by' in rpm_out[0]:
                self.meta['built_from_source'] = True
            else:
                package, version = rpm_out[0].split()

        if 'is not owned by' in rpm_err[0]:
            self.meta['built_from_source'] = True

        if package:
            self.meta['packages'] = {package: version}


class FreebsdNginxMetaCollector(NginxMetaCollector):

    def find_packages(self):
        """ Find a package with running binary """

        # find which package contains our binary
        pkg_out, _ = subp.call('pkg which -p %s' % self.object.bin_path, check=False)
        if 'was installed by package ' in pkg_out[0]:

            # get version
            package, version = pkg_out[0].split()[-1].rsplit('-', 1)
            self.meta['packages'] = {package: version}

        elif 'was not found in the database' in pkg_out[0]:
            self.meta['built_from_source'] = True
