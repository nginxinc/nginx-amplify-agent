# -*- coding: utf-8 -*-
from amplify.agent.objects.abstract import AbstractObject

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


def _version_to_tuple(version):
    return tuple(map(int, str(version).split('.')))


def tuple_to_version(semver):
    return '.'.join(map(str, semver))


class Versions(object):
    def __init__(self, current=None, obsolete=None, old=None):
        self.current = _version_to_tuple(current)
        self.obsolete = _version_to_tuple(obsolete)
        self.old = _version_to_tuple(old)


class ObjectData(object):
    def __init__(self, object=None, config=None, filters=None):
        self.definition = object
        self.id = AbstractObject.hash(self.definition)
        self.type = self.definition.get('type')
        self.config = config if config else {}
        self.config['filters'] = filters or []


class CloudResponse(object):

    def __init__(self, response):
        """
        Init a CloudResponse object

        :param response: {} raw cloud response
        :return: CloudResponse
        """
        self.config = response.get('config', {})
        self.messages = response.get('messages', [])
        self.versions = Versions(**response.get('versions'))
        self.capabilities = response.get('capabilities', {})

        self.objects = []
        for raw_object_data in response.get('objects', []):
            self.objects.append(ObjectData(**raw_object_data))


class HTTP503Error(object):
    """
    Back pressure status handler.
    """

    def __init__(self, http_error):
        """
        Init

        :param http_error: HTTPError object from requests.exceptions
        """
        self.code = 503
        self.text = http_error.response.text or '60'

        try:
            self.delay = int(float(self.text))
        except:
            self.delay = 60

