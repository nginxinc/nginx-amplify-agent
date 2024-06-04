# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, '%s/amplify' % os.getcwd())

from setuptools import setup, find_packages

from amplify.agent.common.util.host import is_deb, is_rpm, is_amazon

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


data_files = [
    ('/etc/amplify-agent/', [
        'etc/agent.conf.default',
    ]),
    ('/etc/logrotate.d/', ['etc/logrotate.d/amplify-agent'])
]

if is_rpm() or is_amazon():
    data_files.append(
        ('/etc/init.d/', ['etc/chkconfig/amplify-agent'])
    )
elif is_deb():
    data_files.append(
        ('/etc/init.d/', ['etc/init.d/amplify-agent']),
    )

setup(
    name="nginx-amplify-agent",
    version="1.8.2",
    author="Mike Belov",
    author_email="dedm@nginx.com",
    description="NGINX Amplify Agent",
    keywords="amplify agent nginx",
    url="https:/amplify.nginx.com/",
    packages=find_packages(
        exclude=[
            "*.test", "*.test.*", "test.*", "test",
            "tools", "tools.*",
            "packages", "packages.*"
        ]
    ),
    package_data={'amplify': [
        'certifi/*.pem',
        'gevent/*.so',
        'gevent/libev/*.so',
        'greenlet/*.so',
        'psutil/*.so',
        '*.so',
    ]},
    data_files=data_files,
    scripts=[
        'nginx-amplify-agent.py'
    ],
    entry_points={},
    long_description='NGINX Amplify Agent',
)
