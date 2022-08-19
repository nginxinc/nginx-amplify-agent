# -*- coding: utf-8 -*-
from amplify.agent.common.context import context

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class AmazonEC2(object):
    """

    Retrieve EC2 metadata

    """
    META_URL = "http://169.254.169.254/latest/meta-data"
    FIELDS = [
        'instance-id', 'hostname', 'local-hostname',
        'public-hostname', 'ami-id', 'local-ipv4',
        'public-keys', 'public-ipv4', 'reservation-id',
    ]

    metadata = {}

    @staticmethod
    def read_meta():
        for field in AmazonEC2.FIELDS:
            try:
                value = context.http_client.get(
                    '%s/%s' % (AmazonEC2.META_URL, field),
                    timeout=0.1, json=False, log=False
                )
                if value is not None:
                    AmazonEC2.metadata[field] = value
            except Exception:
                pass

        return AmazonEC2.metadata

    @staticmethod
    def instance_id():
        try:
            return AmazonEC2.read_meta().get("instance-id", None)
        except Exception:
            return None
