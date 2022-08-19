# -*- coding: utf-8 -*-
import hashlib
import psutil

from amplify.agent.common.context import context
from amplify.agent.common.util import subp
from amplify.agent.managers.abstract import launch_method_supported
from amplify.agent.data.eventd import INFO

from amplify.ext.abstract.manager import ExtObjectManager
from amplify.ext.phpfpm.util.ps import PS_CMD, MASTER_PARSER, PS_PARSER
from amplify.ext.phpfpm.objects.master import PHPFPMObject
from amplify.ext.phpfpm import AMPLIFY_EXT_KEY


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class PHPFPMManager(ExtObjectManager):
    """
    Manager for php-fpm objects.
    """
    ext = AMPLIFY_EXT_KEY

    name = 'phpfpm_manager'
    type = 'phpfpm'
    types = ('phpfpm',)

    def _discover_objects(self):
        # save the current ids
        existing_hashes = [
            obj.definition_hash
            for obj in self.objects.find_all(types=self.types)
        ]
        discovered_hashes = []

        phpfpm_masters = self._find_all()

        while len(phpfpm_masters):
            try:
                data = phpfpm_masters.pop()
                definition = {
                    'type': 'phpfpm',
                    'local_id': data['local_id'],
                    'root_uuid': context.uuid
                }
                definition_hash = PHPFPMObject.hash(definition)
                discovered_hashes.append(definition_hash)

                if definition_hash not in existing_hashes:
                    # New object -- create it
                    new_obj = PHPFPMObject(data=data)

                    # Send discover event.
                    new_obj.eventd.event(
                        level=INFO,
                        message='php-fpm master process found, pid %s' % new_obj.pid
                    )

                    self.objects.register(
                        new_obj, parent_id=self.objects.root_id
                    )
                elif definition_hash in existing_hashes:
                    for obj in self.objects.find_all(types=self.types):
                        if obj.definition_hash == definition_hash:
                            current_obj = obj
                            break

                    if current_obj.pid != data['pid']:
                        # PIDs changed...php-fpm must have been restarted
                        context.log.debug(
                            'php-fpm was restarted (pid was %s now %s)' % (
                                current_obj.pid, data['pid']
                            )
                        )
                        new_obj = PHPFPMObject(data=data)

                        # send php-fpm restart event
                        new_obj.eventd.event(
                            level=INFO,
                            message='php-fpm master process was restarted, new pid %s, old pid %s' % (
                                new_obj.pid, current_obj.pid
                            )
                        )

                        # stop and unregister children
                        for child_obj in self.objects.find_all(
                            obj_id=current_obj.id,
                            children=True,
                            include_self=False
                        ):
                            child_obj.stop()
                            self.objects.unregister(obj=child_obj)

                        # stop old object
                        current_obj.stop()

                        # unregister old object
                        self.objects.unregister(current_obj)

                        self.objects.register(
                            new_obj, parent_id=self.objects.root_id
                        )
            except psutil.NoSuchProcess:
                context.log.debug('phpfpm is restarting/reloading, pids are changing, agent is waiting')

        # check if we left something in objects (phpfpm could be stopped or something)
        dropped_hashes = list(filter(lambda x: x not in discovered_hashes, existing_hashes))

        if len(dropped_hashes) == 0:
            return

        for dropped_hash in dropped_hashes:
            for obj in self.objects.find_all(types=self.types):
                if obj.definition_hash == dropped_hash:
                    dropped_obj = obj

                    context.log.debug(
                        'phpfpm was stopped (pid was %s)' % dropped_obj.pid
                    )

                    for child_obj in self.objects.find_all(
                        obj_id=dropped_obj.id,
                        children=True,
                        include_self=False
                    ):
                        child_obj.stop()
                        self.objects.unregister(child_obj)

                    dropped_obj.stop()
                    self.objects.unregister(dropped_obj)

    @staticmethod
    def _find_all(ps=None):
        """
        Tries to find a master process

        :param ps: List of Strings...used for debugging our parsing logic... should be None most of the time
        :return: List of Dicts phpfpm object definitions
        """
        # get ps info
        try:
            # set ps output to passed param or call subp
            ps, _ = (ps, None) if ps is not None else subp.call(PS_CMD)
            context.log.debug('ps php-fpm output: %s' % ps)
        except Exception as e:
            # log error
            exception_name = e.__class__.__name__
            context.log.debug(
                'failed to find running php-fpm via "%s" due to %s' % (
                    PS_CMD, exception_name
                )
            )
            context.log.debug('additional info:', exc_info=True)

            # If there is a root_object defined, log an event to send to the
            # cloud.
            if context.objects.root_object:
                context.objects.root_object.eventd.event(
                    level=INFO,
                    message='no php-fpm found'
                )

            # break processing returning a fault-tolerant empty list
            return []

        if not any('master process' in line for line in ps):
            context.log.info('no php-fpm masters found')

            # break processing returning a fault-tolerant empty list
            return []

        # collect all info about processes
        masters = {}
        try:
            for line in ps:
                parsed = PS_PARSER(line)

                # if not parsed - go to the next line
                if parsed is None:
                    continue

                pid, ppid, cmd = parsed  # unpack values

                # match master process
                if 'master process' in cmd:
                    if not launch_method_supported("php-fpm", ppid):
                        continue

                    try:
                        conf_path = MASTER_PARSER(cmd)
                    except:
                        context.log.error(
                            'failed to find conf_path for %s' % cmd
                        )
                        context.log.debug('additional info:', exc_info=True)
                    else:
                        # calculate local_id
                        local_string_id = '%s_%s' % (cmd, conf_path)
                        local_id = hashlib.sha256(local_string_id.encode('utf-8')).hexdigest()

                        if pid not in masters:
                            masters[pid] = {'workers': []}

                        masters[pid].update({
                            'cmd': cmd.strip(),
                            'conf_path': conf_path,
                            'pid': pid,
                            'local_id': local_id
                        })

                # match pool process
                elif 'pool' in cmd:
                    if ppid in masters:
                        masters[ppid]['workers'].append(pid)
                    else:
                        masters[ppid] = dict(workers=[pid])

        except Exception as e:
            # log error
            exception_name = e.__class__.__name__
            context.log.error(
                'failed to parse ps results due to %s' % exception_name
            )
            context.log.debug('additional info:', exc_info=True)

        # format results
        results = []
        for payload in masters.values():
            # only add payloads that have all the keys
            if 'cmd' in payload and \
                    'conf_path' in payload and \
                    'pid' in payload and \
                    'local_id' in payload and \
                    'workers' in payload:
                results.append(payload)
            else:
                context.log.debug(
                    'phpfpm master "_find_all()" found an incomplete entity %s'
                    % payload
                )
        return results
