# -*- coding: utf-8 -*-
import re


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


PS_CMD = "ps xao pid,ppid,command | grep 'php-fpm[:]'"


_PS_REGEX = re.compile(r'\s*(?P<pid>\d+)\s+(?P<ppid>\d+)\s+(?P<cmd>.+)\s*')


def PS_PARSER(ps_line):
    # parse ps response line...examples::
    #    36     1 php-fpm: master process (/etc/php/7.0/fpm/php-fpm.conf)
    #    37    36 php-fpm: pool www
    #    38    36 php-fpm: pool www
    parsed = _PS_REGEX.match(ps_line)

    if not parsed:
        return None

    pid, ppid, cmd = int(parsed.group('pid')), int(parsed.group('ppid')), parsed.group('cmd').rstrip()
    return pid, ppid, cmd


_PS_MASTER_REGEX = re.compile(r'.*\((?P<conf_path>\/[^\)]*)\).*')


def MASTER_PARSER(ps_master_cmd):
    # parse ps master cmd line...:
    #   php-fpm: master process (/etc/php/7.0/fpm/php-fpm.conf)
    parsed = _PS_MASTER_REGEX.match(ps_master_cmd)

    if not parsed:
        return None

    conf_path = parsed.group('conf_path')
    return conf_path


LS_CMD = "ls -la /proc/%s/exe"
LS_CMD_FREEBSD = "ls -la /proc/%s/file"


_LS_REGEX = re.compile(r'.+\-\>\s*(?P<bin_path>.+)\s*')


def LS_PARSER(ls_cmd_line):
    # parse ls cmd line...:
    #   lrwxrwxrwx 1 root root 0 Oct  8 07:09 /proc/2508/exe -> /usr/sbin/php5-fpm
    # or
    #   lrwxrwxrwx 1 root root 0 Mar 31 15:21 /proc/41/exe -> /usr/sbin/php-fpm7.0
    parsed = _LS_REGEX.match(ls_cmd_line)

    if not parsed:
        return None

    return parsed.group('bin_path')
