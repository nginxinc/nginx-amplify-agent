# -*- coding: utf-8 -*-
import os

from amplify.agent.common.util import subp
from amplify.agent.common.context import context


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


def is_docker():
    """
    Docker wants you to use their external API when trying to gain information/self-awareness of container state:

    https://docs.docker.com/engine/reference/api/docker_remote_api/

    The problem is that this API is optional and does not have a standard location from within a container (or rather it
    can be configured to listen anywhere).  Instead, this check will parse the `/proc` filesystem trying to parse the
    docker ID from the output.  If we find an ID, we will assume that we are in a docker container.

    :return: Bool True if docker ID is found, False otherwise.
    """
    try:
        stdout, _ = subp.call('cat /proc/self/cgroup | fgrep -e docker | head -n 1 | sed "s/.*docker\/\(.*\)/\\1/"')
        docker_id = stdout[0]
        return len(docker_id) == 64 and ' ' not in docker_id

    except Exception as e:
        context.log.error('failed to find docker id due to %s' % e.__class__.__name__)
        context.log.debug('additional info:', exc_info=True)
        return False


def is_lxc():
    """
    LXC sets an environment variable 'container' equal to 'lxc' when inside a continer.

    :return: Bool True if 'lxc', False otherwise.
    """
    container_env = os.environ.get('container')
    return container_env == 'lxc'


CONTAINER_MAP = {
    'docker': is_docker,
    'lxc': is_lxc
}


def container_environment():
    for container_type, check in CONTAINER_MAP.items():
        if check():
            return container_type
