# -*- coding: utf-8 -*-
from amplify.agent.common.context import context


__author__ = "Raymond Lau"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Raymond Lau"
__email__ = "raymond.lau@nginx.com"


SUPPORTED_API_VERSIONS = [2]


def get_latest_supported_api(location_prefix, timeout=1, log=False):
    """
    Hitting the location prefix for the API returns a list of supported API versions.  This
    function hits that endpoint and returns a URI to the current API version.

    It's not mentioned in the api documentation if list of versions is guaranteed to be ordered
    or if they can be 2.1, 2.2, etc. so doing some extra checking here to make sure
    the actual latest version is taken, instead of just getting the value at the end of the list
    :param location_prefix: str (ex. http://demo.nginx.com/api/)
    :param timeout: Int
    :param log: Boolean
    :return: str
    """
    api_versions_list = context.http_client.get(location_prefix, timeout=timeout, log=log)
    supported_by_agent = set(api_versions_list).intersection(set(SUPPORTED_API_VERSIONS))
    if len(supported_by_agent) == 0:
        context.log.debug("No Nginx+ API versions %s are supported by this agent (%s)." % (api_versions_list, supported_by_agent))
        return None
    latest_supported_version = max(supported_by_agent)
    api_uri = location_prefix
    if api_uri[-1] != '/':
        api_uri += '/'
    api_uri += "%s" % latest_supported_version
    return api_uri


def _traverse_versioned_plus_api(api_url, timeout=1, log=False, root_endpoints_to_skip=None):
    """
    Get data from all of the Plus API endpoints and combine them into a
    single dict, similar to how the now-deprecated plus status module would
    return everything at once

    ex. api_url=http://demo.nginx.com/api/2 returns a list of endpoints
    ["nginx","processes","connections", ...]
    so we will call this func on /api/2/nginx, /api/2/processes,
    /api/2/connections, and so on.
    If it returns a json dictionary, we just take the output and return.

    http://demo.nginx.com/api/2
    :param api_url: str - base API endpoint
    :return: dict containing aggregated responses of all the api endpoints
    {
        "processes" : {             #output of /api/2/processes
            "respawned: : 0
        },
        "nginx" : {...},            #output of /api/2/nginx
        "connections" : {...},
        "ssl" : {...},
        "http" : {
            "caches" : {            #output of /api/2/http/caches
                "http_cache" : {...},
                ...
            },
            "keyvals" : {           #output of /api/2/http/keyvals
                "nginx_plus_versions" : {...},
                ...
            },
            ....
        },
        "stream" : {
            "server_zones" : {      #output of /api/2/stream/server_zones
                "postgresql_loadbalancer" : {...},
                ...
            },
            ...
        },
        "slabs" : {...}
        ...
    }

    """
    aggregated_responses = {}

    try:
        api_response = context.http_client.get(
            api_url,
            timeout=timeout,
            log=log
        )
    except Exception as e:
        context.log.error(
            'Caught "%s" error during api traverse' % e.__class__.__name__
        )
        context.log.debug('additional info:', exc_info=True)
        api_response = {}

    if isinstance(api_response, list):
        for endpoint in api_response:
            if root_endpoints_to_skip is not None and endpoint in root_endpoints_to_skip:
                aggregated_responses[endpoint] = {}
                continue
            api_response = _traverse_versioned_plus_api("%s/%s" % (api_url, endpoint), timeout=timeout, log=log)
            aggregated_responses[endpoint] = api_response
    elif isinstance(api_response, dict):
        aggregated_responses = api_response

    return aggregated_responses


def traverse_plus_api(location_prefix, timeout=1, log=False, root_endpoints_to_skip=None):
    """
    Does basically the same thing as traverse_versioned_plus_api except that it gets the
    current API from root endpoint before and traverses based on that

    :param location_prefix: str (ex. http://demo.nginx.com/api/)
    :param timeout:
    :param log:
    :param root_endpoints_to_skip: list of strings
    :return: dict containing aggregated responses of all the api endpoints
    """
    current_api = get_latest_supported_api(location_prefix, timeout, log)
    if current_api is None:
        return None
    return _traverse_versioned_plus_api(current_api, timeout, log, root_endpoints_to_skip)
