# -*- coding: utf-8 -*-
import hashlib
import re

import psutil

from amplify.agent.data.eventd import INFO
from amplify.agent.common.util import subp
from amplify.agent.common.context import context
from amplify.agent.managers.abstract import ObjectManager, launch_method_supported
from amplify.agent.objects.nginx.object import NginxObject, ContainerNginxObject
from amplify.agent.objects.nginx.binary import get_prefix_and_conf_path

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class NginxManager(ObjectManager):
    """
    Manager for Nginx objects.
    """
    name = 'nginx_manager'
    type = 'nginx'
    types = ('nginx', 'container_nginx')

    def _init_nginx_object(self, data=None):
        """
        Method for initializing a new NGINX object.  Checks to see if we need a
        Docker object or a regular one.

        :param data: Dict Data dict for object init
        :return: NginxObject/ContainerNginxObject
        """
        if self.in_container:
            return ContainerNginxObject(data=data)
        else:
            return NginxObject(data=data)

    def _restart_nginx_object(self, current_obj, data):
        """
        Restarts an object by initiaizing a new object with new data, stopping
        and unregistering children of old object, replacing old object with new
        object in the object tank, and finally stopping the old object.

        There are two conditions that can trigger a restart which is why this
        logic is moved to an encapsulated function.
        """
        context.log.debug(
            'nginx object restarting (master pid was %s)' % current_obj.pid
        )
        # push cloud config
        data.update(self.object_configs.get(current_obj.definition_hash, {}))

        # pass on data from the last config collection to the new object
        config_collector = current_obj.collectors[0]
        data['config_data'] = {
            'previous': config_collector.previous
        }

        # if there is information in the configd store, pass it from old to new object
        if current_obj.configd.current:
            data['configd'] = current_obj.configd

        # also pass on reloads counter
        data['reloads'] = current_obj.reloads

        new_obj = self._init_nginx_object(data=data)

        # Send nginx config changed event.
        new_obj.eventd.event(
            level=INFO,
            message='nginx-%s config changed, read from %s' % (
                new_obj.version, new_obj.conf_path
            )
        )

        new_obj.id = current_obj.id

        # stop and deregister children
        for child_obj in self.objects.find_all(
                obj_id=current_obj.id,
                children=True,
                include_self=False
        ):
            child_obj.stop()
            self.objects.unregister(obj=child_obj)

        # Replace old object in tank.
        self.objects.objects[current_obj.id] = new_obj
        current_obj.stop()  # stop old object

    def _discover_objects(self):
        # save the current_ids
        existing_hashes = [obj.definition_hash for obj in self.objects.find_all(types=self.types)]

        # discover nginxs
        nginxs = self._find_all()

        # process all found nginxs
        discovered_hashes = []
        while len(nginxs):
            try:
                definition, data = nginxs.pop()
                definition_hash = NginxObject.hash(definition)
                discovered_hashes.append(definition_hash)

                if definition_hash not in existing_hashes:
                    # New object -- create it
                    data.update(self.object_configs.get(definition_hash, {}))  # push cloud config
                    new_obj = self._init_nginx_object(data=data)
                    # Send discover event.
                    new_obj.eventd.event(
                        level=INFO,
                        message='nginx-%s master process found, pid %s' % (new_obj.version, new_obj.pid)
                    )
                    self.objects.register(new_obj, parent_id=self.objects.root_id)
                elif definition_hash in existing_hashes:
                    for obj in self.objects.find_all(types=self.types):
                        if obj.definition_hash == definition_hash:
                            current_obj = obj
                            break  # TODO: Think about adding a definition hash - id map to objects tank.

                    if current_obj.need_restart:
                        # restart object if needed
                        self._restart_nginx_object(current_obj, data)

                        # this usually is triggered by bubbled errors from
                        # coroutine errors...this should not typically happen
                        # but is included for resilience.
                        context.log.debug(
                            'nginx object was restarted by "need_restart" flag'
                        )
                    elif current_obj.pid != data['pid']:
                        # check that the object pids didn't change
                        context.log.debug(
                            'nginx was restarted (pid was %s now %s)' % (
                                current_obj.pid, data['pid']
                            )
                        )
                        data.update(self.object_configs.get(definition_hash, {}))

                        new_obj = self._init_nginx_object(data=data)

                        # Send nginx master process restart event.
                        new_obj.eventd.event(
                            level=INFO,
                            message='nginx-%s master process restarted, new pid %s, old pid %s' % (
                                new_obj.version,
                                new_obj.pid,
                                current_obj.pid
                            )
                        )

                        new_obj.id = current_obj.id

                        # stop and unregister children
                        for child_obj in self.objects.find_all(
                                obj_id=current_obj.id,
                                children=True,
                                include_self=False
                        ):
                            child_obj.stop()
                            self.objects.unregister(obj=child_obj)

                        self.objects.objects[current_obj.id] = new_obj
                        current_obj.stop()  # stop old object
                    elif current_obj.workers != data['workers']:
                        # this is a reload, increment counter
                        current_obj.reloads += 1
                        # if workers changed nginx was reloaded
                        context.log.debug(
                            'nginx was reloaded (workers were %s now %s)' % (
                                current_obj.workers, data['workers']
                            )
                        )
                        self._restart_nginx_object(current_obj, data)
            except psutil.NoSuchProcess:
                context.log.debug('nginx is restarting/reloading, pids are changing, agent is waiting')

        # check if we left something in objects (nginx could be stopped or something)
        dropped_hashes = list(filter(lambda x: x not in discovered_hashes, existing_hashes))

        if len(dropped_hashes):
            for dropped_hash in dropped_hashes:
                for obj in self.objects.find_all(types=self.types):
                    if obj.definition_hash == dropped_hash:
                        dropped_obj = obj
                        break  # TODO: Think about adding a definition hash - id map to objects tank.

                context.log.debug('nginx was stopped (pid was %s)' % dropped_obj.pid)

                for child_obj in self.objects.find_all(
                        obj_id=dropped_obj.id,
                        children=True,
                        include_self=False
                ):
                    child_obj.stop()
                    self.objects.unregister(child_obj)

                dropped_obj.stop()
                self.objects.unregister(dropped_obj)

        # manage nginx configs
        self._manage_configs()

    @staticmethod
    def _find_all():
        """
        Tries to find all master processes

        :return: list of dict: nginx object definitions
        """
        # get ps info
        ps_cmd = "ps xao pid,ppid,command | grep 'nginx[:]'"
        try:
            ps, _ = subp.call(ps_cmd)
            context.log.debug('ps nginx output: %s' % ps)
        except:
            context.log.debug('failed to find running nginx via %s' % ps_cmd)
            context.log.debug('additional info:', exc_info=True)
            if context.objects.root_object:
                context.objects.root_object.eventd.event(
                    level=INFO,
                    message='no nginx found'
                )
            return []

        # return an empty list if there are no master processes
        if not any('nginx: master process' in line for line in ps):
            context.log.debug('nginx masters amount is zero')
            return []

        # collect all info about processes
        masters = {}
        try:
            for line in ps:
                # parse ps response line:
                # 21355     1 nginx: master process /usr/sbin/nginx
                gwe = re.match(r'\s*(?P<pid>\d+)\s+(?P<ppid>\d+)\s+(?P<cmd>.+)\s*', line)

                # if not parsed - go to the next line
                if not gwe:
                    continue

                pid, ppid, cmd = int(gwe.group('pid')), int(gwe.group('ppid')), gwe.group('cmd').rstrip()

                # match nginx master process
                if 'nginx: master process' in cmd:
                    if not launch_method_supported("nginx", ppid):
                        continue

                    # get path to binary, prefix and conf_path
                    try:
                        bin_path, prefix, conf_path, version = get_prefix_and_conf_path(cmd)
                    except:
                        context.log.debug('failed to find bin_path, prefix and conf_path for %s' % cmd)
                        context.log.debug('', exc_info=True)
                    else:
                        # calculate local id
                        local_string_id = '%s_%s_%s' % (bin_path, conf_path, prefix)
                        local_id = hashlib.sha256(local_string_id.encode('utf-8')).hexdigest()

                        if pid not in masters:
                            masters[pid] = {'workers': []}

                        masters[pid].update({
                            'version': version,
                            'bin_path': bin_path,
                            'conf_path': conf_path,
                            'prefix': prefix,
                            'pid': pid,
                            'local_id': local_id
                        })

                # match worker process
                elif 'nginx: worker process' in cmd:
                    if ppid in masters:
                        masters[ppid]['workers'].append(pid)
                    else:
                        masters[ppid] = dict(workers=[pid])
        except Exception as e:
            exception_name = e.__class__.__name__
            context.log.error('failed to parse ps results due to %s' % exception_name)
            context.log.debug('additional info:', exc_info=True)

        # collect results
        results = []
        for pid, description in masters.items():
            if 'bin_path' in description:  # filter workers with non-executable nginx -V (relative paths, etc)
                definition = {
                    'local_id': description['local_id'],
                    'type': NginxManager.type,
                    'root_uuid': context.uuid
                }
                results.append((definition, description))
        return results

    def _manage_configs(self):
        # go through existing objects and create the ident tags for their configs
        existing_object_configs = set()
        for nginx_obj in self.objects.find_all(types=self.types):
            existing_object_configs.add((nginx_obj.conf_path, nginx_obj.prefix, nginx_obj.bin_path))

        # create a set of the existing ident tags
        configs = set(context.nginx_configs.keys())

        # for the idents in the tank but not being referenced by existing nginx objects, remove them
        for filename, prefix, bin_path in configs.difference(existing_object_configs):
            del context.nginx_configs[(filename, prefix, bin_path)]
