# -*- coding: utf-8 -*-


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class AmplifyException(Exception):
    description = 'Something really bad happened'

    def __init__(self, message=None, payload=None):
        Exception.__init__(self)
        self.message = message
        self.payload = payload

    def to_dict(self):
        return {
            'error': self.__class__.__name__,
            'description': self.description,
            'message': self.message,
            'payload': dict(self.payload or ())
        }

    def __str__(self):
        return "(message=%s, payload=%s)" % (self.message, self.payload)


class AmplifyCriticalException(AmplifyException):
    description = 'DOOM 2: Hell on the Earth'


class AmplifyParseException(AmplifyException):
    description = "Couldn't parse something critical"


class AmplifyFileTooLarge(AmplifyException):
    description = "Config file too large"


class AmplifySubprocessError(AmplifyException):
    description = "Subprocess finished with non-zero code"
