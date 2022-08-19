# -*- coding: utf-8 -*-
import re

from amplify.agent.common.context import context
from amplify.agent.common.util import subp


__author__ = "Andrew Alexeev"
__copyright__ = "Copyright (C) Nginx Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


PS_CMD = "ps xao pid,ppid,command | grep -E 'mysqld( |$)'"  # grep -P doesn't work on BSD systems
PS_REGEX = re.compile(r'\s*(?P<pid>\d+)\s+(?P<ppid>\d+)\s+(?P<cmd>.+)\s*')

LS_CMD = "ls -la /proc/%s/exe"
LS_CMD_FREEBSD = "ls -la /proc/%s/file"
LS_REGEX = re.compile(r'.+\-\>\s*(?P<bin_path>.+)\s*')

VERSION_CMD = "%s -V"


def ps_parser(ps_line):
    """
    parses PS response line, for example
    26753     1 /usr/sbin/mysqld

    :param ps_line: str ps line
    :return: (int pid, int ppid, str cmd)
    """
    parsed = PS_REGEX.match(ps_line)

    if not parsed:
        return None

    pid, ppid, cmd = int(parsed.group('pid')), int(parsed.group('ppid')), parsed.group('cmd')
    return pid, ppid, cmd


def master_parser(ps_master_cmd=None):
    """
    TODO:

    we might want to add the actual parser for the config options some day, e.g.
        --defaults-file=#        Only read default options from the given file #.
        --defaults-extra-file=#  Read this file after the global files are read.
        --socket=name            Socket file to use for connection
        -P, --port=#
        --bind-address=name

    For now it's a static path here

    :param ps_master_cmd: str master cmd
    :return: path to config
    """
    conf_path = "/etc/mysql/my.cnf"
    return conf_path


def ls_parser(ls_cmd_line):
    """
    Parses ls output on proc file  and returns real bin path

    lrwxrwxrwx 1 root root 0 Jul 27 16:01 /proc/26753/exe -> /usr/sbin/mysqld

    :param ls_cmd_line: str ls line
    :return: str bin path
    """
    parsed = LS_REGEX.match(ls_cmd_line)

    if not parsed:
        return None

    return parsed.group('bin_path')


def version_parser(bin_path):
    """
    Runs version command and parses verson of mysqld

    :param bin_path: str bin path
    :return: str version
    """
    try:
        raw_stdout, _ = subp.call(VERSION_CMD % bin_path)

        # also trying to get the first line of output
        # here's the line that we are interested in::
        # mysqld  Ver 5.5.55-0ubuntu0.14.04.1 for debian-linux-gnu on x86_64 ((Ubuntu))
        raw_line = raw_stdout[0]
    except Exception as e:
        exc_name = e.__class__.__name__
        # this is being logged as debug only since we will rely on bin_path
        # collection error to tip off support as to what is going wrong with
        # version detection
        context.log.debug(
            'failed to get version info from "%s" due to %s' %
            (bin_path, exc_name)
        )
        context.log.debug('additional info:', exc_info=True)
    else:
        raw_version = raw_line.split()[2]  # 5.5.55-0ubuntu0.14.04.1

        version = []
        for char in raw_version:
            if char.isdigit() or char == '.':
                version.append(char)
            else:
                break

        return ''.join(version), raw_line
