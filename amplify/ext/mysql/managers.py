# -*- coding: utf-8 -*-
import hashlib
import psutil

from amplify.agent.common.context import context
from amplify.agent.common.util import subp
from amplify.agent.managers.abstract import launch_method_supported
from amplify.agent.data.eventd import INFO
from amplify.ext.abstract.manager import ExtObjectManager
from amplify.ext.mysql.util import PS_CMD, master_parser, ps_parser
from amplify.ext.mysql import AMPLIFY_EXT_KEY
from amplify.agent.common.util.configtypes import boolean
from amplify.ext.mysql.objects import MySQLObject


__author__ = "Andrew Alexeev"
__copyright__ = "Copyright (C) Nginx Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class MySQLManager(ExtObjectManager):
    """
    Manager for MySQL objects.
    """
    ext = AMPLIFY_EXT_KEY

    name = 'mysql_manager'
    type = 'mysql'
    types = ('mysql',)

    def _discover_objects(self):
        # save the current ids
        existing_hashes = [
            obj.definition_hash
            for obj in self.objects.find_all(types=self.types)
        ]
        discovered_hashes = []

        if boolean(context.app_config['mysql'].get('remote', False)):
            mysql_daemons = self._find_remote()
        else:
            mysql_daemons = self._find_local()

        while len(mysql_daemons):
            try:
                data = mysql_daemons.pop()

                definition = {
                    'type': 'mysql',
                    'local_id': data['local_id'],
                    'root_uuid': context.uuid
                }
                definition_hash = MySQLObject.hash(definition)
                discovered_hashes.append(definition_hash)

                if definition_hash not in existing_hashes:
                    # New object -- create it
                    new_obj = MySQLObject(data=data)

                    # Send discover event.
                    new_obj.eventd.event(
                        level=INFO,
                        message='mysqld process found, pid %s' % new_obj.pid
                    )

                    self.objects.register(new_obj, parent_id=self.objects.root_id)

                elif definition_hash in existing_hashes:
                    for obj in self.objects.find_all(types=self.types):
                        if obj.definition_hash == definition_hash:
                            current_obj = obj
                            break

                    if current_obj.pid != data['pid']:
                        # PIDs changed... MySQL must have been restarted
                        context.log.debug(
                            'mysqld was restarted (pid was %s now %s)' % (
                                current_obj.pid, data['pid']
                            )
                        )
                        new_obj = MySQLObject(data=data)

                        # send MySQL restart event
                        new_obj.eventd.event(
                            level=INFO,
                            message='mysqld process was restarted, new  pid %s, old pid %s' % (
                                new_obj.pid,
                                current_obj.pid
                            )
                        )

                        # stop and un-register children
                        children_objects = self.objects.find_all(
                            obj_id=current_obj.id,
                            children=True,
                            include_self=False
                        )

                        for child_obj in children_objects:
                            child_obj.stop()
                            self.objects.unregister(obj=child_obj)

                        # un-register old object
                        self.objects.unregister(current_obj)

                        # stop old object
                        current_obj.stop()

                        self.objects.register(new_obj, parent_id=self.objects.root_id)
            except psutil.NoSuchProcess:
                context.log.debug('mysqld is restarting/reloading, pids are changing, agent is waiting')

        # check if we left something in objects (MySQL could be stopped or something)
        dropped_hashes = list(filter(lambda x: x not in discovered_hashes, existing_hashes))

        if len(dropped_hashes) == 0:
            return

        for dropped_hash in dropped_hashes:
            for obj in self.objects.find_all(types=self.types):
                if obj.definition_hash == dropped_hash:
                    dropped_obj = obj
                    break

        context.log.debug('mysqld was stopped (pid was %s)' % dropped_obj.pid)

        # stop and un-register children
        children_objects = self.objects.find_all(
            obj_id=dropped_obj.id,
            children=True,
            include_self=False
        )

        for child_obj in children_objects:
            child_obj.stop()
            self.objects.unregister(child_obj)

        dropped_obj.stop()
        self.objects.unregister(dropped_obj)

    @staticmethod
    def _find_local(ps=None):
        """
        Tries to find all mysqld processes

        :param ps: [] of str, used for debugging our parsing logic - should be None most of the time
        :return: [] of {} MySQL object definitions
        """
        # get ps info
        try:
            # set ps output to passed param or call subp
            ps, _ = (ps, None) if ps is not None else subp.call(PS_CMD)
            context.log.debug('ps mysqld output: %s' % ps)
        except Exception as e:
            # log error
            exception_name = e.__class__.__name__
            context.log.debug(
                'failed to find running mysqld via "%s" due to %s' % (
                    PS_CMD, exception_name
                )
            )
            context.log.debug('additional info:', exc_info=True)

            # If there is a root_object defined, log an event to send to the
            # cloud.
            if context.objects.root_object:
                context.objects.root_object.eventd.event(
                    level=INFO,
                    message='no mysqld processes found'
                )

            # break processing returning a fault-tolerant empty list
            return []

        if not any('mysqld' or 'mariadbd' in line for line in ps):
            context.log.info('no mysqld processes found')

            # break processing returning a fault-tolerant empty list
            return []

        # collect all info about processes
        masters = {}
        try:
            for line in ps:
                parsed = ps_parser(line)

                # if not parsed - go to the next line
                if parsed is None:
                    continue

                pid, ppid, cmd = parsed  # unpack values

                # match master process
                if cmd.split(' ', 1)[0].endswith('d'):
                    if not launch_method_supported("mysql", ppid):
                        continue

                    try:
                        conf_path = master_parser(cmd)
                    except Exception as e:
                        context.log.error('failed to find conf_path for %s' % cmd)
                        context.log.debug('additional info:', exc_info=True)
                    else:
                        # calculate local_id
                        local_string_id = '%s_%s' % (cmd, conf_path)
                        local_id = hashlib.sha256(local_string_id.encode('utf-8')).hexdigest()

                        if pid not in masters:
                            masters[pid] = {}

                        masters[pid].update({
                            'cmd': cmd.strip(),
                            'conf_path': conf_path,
                            'pid': pid,
                            'local_id': local_id
                        })
        except Exception as e:
            # log error
            exception_name = e.__class__.__name__
            context.log.error('failed to parse ps results due to %s' % exception_name)
            context.log.debug('additional info:', exc_info=True)

        # format results
        results = []
        for payload in masters.values():
            # only add payloads that have all the keys
            if 'cmd' in payload and 'conf_path' in payload and 'pid' in payload and 'local_id' in payload:
                results.append(payload)
            else:
                context.log.debug('MySQL "_find_all()" found an incomplete entity %s' % payload)

        return results

    @staticmethod
    def _find_remote():
        """
        :return: [] of {} MySQL object definition for remote mysqld process
        """
        results = []

        try:
            cmd = "/usr/sbin/mysqld"
            conf_path = "/etc/mysql/my.cnf"

            # calculate local_id
            local_string_id = '%s_%s' % (cmd, conf_path)
            local_id = hashlib.sha256(local_string_id.encode('utf-8')).hexdigest()
            results.append({
                'cmd': 'unknown',
                'conf_path': 'unknown',
                'pid': 'unknown',
                'local_id': local_id
            })
        except Exception as e:
            # log error
            exception_name = e.__class__.__name__
            context.log.error('failed to parse remote mysql results due to %s' % exception_name)
            context.log.debug('additional info:', exc_info=True)

        return results
