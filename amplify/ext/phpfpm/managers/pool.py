# -*- coding: utf-8 -*-
import psutil

from amplify.agent.common.context import context
from amplify.agent.data.eventd import INFO

from amplify.ext.abstract.manager import ExtObjectManager
from amplify.ext.phpfpm.objects.pool import PHPFPMPoolObject
from amplify.ext.phpfpm import AMPLIFY_EXT_KEY


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class PHPFPMPoolManager(ExtObjectManager):
    """
    Manager for php-fpm pools.
    """
    ext = AMPLIFY_EXT_KEY

    name = 'phpfpm_pool_manager'
    type = 'phpfpm_pool'
    types = ('phpfpm_pool',)

    def _discover_objects(self):
        # save the current hashes
        existing_hashes = [
            obj.definition_hash
            for obj in self.objects.find_all(types=self.types)
        ]
        discovered_pools = self._find_all()

        while len(discovered_pools):
            try:
                data = discovered_pools.pop()
                definition = {
                    'type': 'phpfpm_pool',
                    'local_id': data['local_id'],
                    'root_uuid': context.uuid
                }
                definition_hash = PHPFPMPoolObject.hash(definition)

                if definition_hash not in existing_hashes:
                    # new object -- create it
                    new_obj = PHPFPMPoolObject(data=data)

                    # send discover event
                    new_obj.eventd.event(
                        level=INFO,
                        message='php-fpm pool found, name "%s"' % new_obj.name
                    )

                    self.objects.register(new_obj, parent_id=data['parent_id'])

                # We don't need restart logic since the master process should
                # take care of child objects.
            except psutil.NoSuchProcess:
                context.log.debug('phpfpm is restarting/reloading, pids are changing, agent is waiting')

        # We also don't need stop logic since the master process should take
        # care of child objects.

    def _find_all(self):
        """
        Go through the masters.  For the masters go through the configured
        pools, update pooldata with parent_local_id and local_id hash data.
        Then add the new updated pool to results and return completed dicts.

        :return: List of Dict data representations of object meta data.
        """
        phpfpm_masters = self.objects.find_all(types=('phpfpm',))
        phpfpm_pools = []

        for master in phpfpm_masters:
            master_config = master.parse()

            for pool_data in master_config['pools']:
                # if there are no "missing" (None) values...
                if not len(list(filter(lambda x: x is None, pool_data.values()))):
                    # ...proceed with creation of a pool object for management
                    pool_data.update(parent_id=master.id)
                    pool_data.update(parent_local_id=master.local_id)
                    pool_local_id = (
                        pool_data['parent_local_id'], pool_data['name']
                    )
                    pool_data.update(
                        local_id=PHPFPMPoolObject.hash_local(pool_local_id)
                    )
                    phpfpm_pools.append(pool_data)
                else:
                    # create list of keys with None values
                    none_keys = map(
                        lambda t: t[0],
                        filter(
                            lambda t: t[1] is None,
                            [(k, v) for k, v in pool_data.items()]
                        )
                    )

                    # ...log debug and skip
                    context.log.debug(
                        'found a pool "%s" with missing or commented directives %s %s' % (
                            pool_data['name'],
                            ', '.join(['"%s"' % key for key in none_keys]),
                            pool_data
                        )
                    )

        return phpfpm_pools
