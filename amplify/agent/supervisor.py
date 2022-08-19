# -*- coding: utf-8 -*-
import copy
import pprint
import time
import gevent
import atexit

from threading import current_thread
from requests.exceptions import HTTPError

from amplify.agent.common.cloud import CloudResponse, HTTP503Error, tuple_to_version
from amplify.agent.common.context import context
from amplify.agent.common.util.backoff import exponential_delay
from amplify.agent.common.errors import AmplifyCriticalException
from amplify.agent.common.util import loader
from amplify.agent.common.util.threads import spawn
from amplify.agent.common.util.system import get_root_definition
from amplify.agent.managers.bridge import Bridge


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class Supervisor(object):
    """
    Agent supervisor

    Starts dedicated threads for each manager.
    """
    # TODO: Unify the manager init and supervision process (object managers vs. bridge)

    MANAGER_CLASS = '%sManager'
    MANAGER_MODULE = 'amplify.agent.managers.%s.%s'

    def __init__(self, foreground=False, debug=False):
        """
        Supervisor constructor

        :param foreground: bool run in foreground if True
        :param debug: bool run in debug mode if True
        """
        # daemon specific
        self.stdin_path = '/dev/null'

        if foreground or debug:
            self.stdout_path = '/dev/stdout'
            self.stderr_path = '/dev/stderr'
        else:
            self.stdout_path = '/dev/null'
            self.stderr_path = '/dev/null'

        self.pidfile_path = context.app_config['daemon']['pid']
        self.pidfile_timeout = 1

        # init
        self.object_managers = {}
        self.object_manager_order = ['system', 'nginx', 'status', 'api']
        self.external_object_manager_types = []
        self.external_managers = {}
        self.external_modules = []
        self.bridge = None
        self.bridge_object = None
        self.start_time = int(time.time())
        self.last_cloud_talk_time = 0
        self.last_cloud_talk_restart = 0
        self.cloud_talk_fails = 0
        self.cloud_talk_delay = 0
        self.is_running = True

        # debug mode parameters
        self.debug_mode = debug
        self.debug_mode_time = 300  # five minutes

    def init_object_managers(self):
        """
        Tries to load and create all internal object managers specified in config
        """
        for object_type in self.object_manager_order:
            try:
                object_manager_classname = self.MANAGER_CLASS % object_type.title()
                manager_class = loader.import_class(self.MANAGER_MODULE % (object_type, object_manager_classname))

                # copy object configs
                if object_type in self.object_managers:
                    object_configs = copy.copy(self.object_managers[object_type].object_configs)
                else:
                    object_configs = None

                self.object_managers[object_type] = manager_class(
                    object_configs=object_configs
                )
                context.log.debug('loaded "%s" object manager from %s' % (object_type, manager_class))
            except:
                context.log.error('failed to load %s object manager' % object_type, exc_info=True)

    def load_ext_managers(self):
        """
        Tries to load and create all ext managers to be run during primary event loop.
        """
        import pkgutil
        import inspect
        import amplify.ext as extensions
        from amplify.agent.common.util.configtypes import boolean
        from amplify.ext.abstract.manager import (
            AbstractExtManager, ExtObjectManager
        )
        from amplify.ext.abstract.config import AbstractExtConfig

        base_prefix = extensions.__name__ + '.'  # 'amplify.ext.'

        def enabled_extension(modname):
            # not defined in the config
            if modname not in context.app_config.get('extensions', {}):
                return False

            # not enabled
            if not boolean(context.app_config.get('extensions', {}).get(modname, False)):
                return False

            # not enabled in backend
            if not context.capabilities[modname]:
                return False

            return True

        def _recursive_manager_init(inspected_package, prefix=base_prefix, top_mod=None):
            """
            Takes a package and iterates all of the modules.  If it's a module (e.g. not a package), it will look for
            ObjectManager class definitions and add and instance of it to the object_managers store.

            :param inspected_package: Package
            :return: List Module names inspected by the call
            """
            passed_top_mod = top_mod is not None
            module_paths = dict()

            # iter all modules in package
            for _, modname, ispkg in pkgutil.iter_modules(inspected_package.__path__):
                # add module name as the start of an inner modpath
                new_mod_path = {
                    modname: None
                }

                # set the top_mod if not passed from outer scope
                if not passed_top_mod:
                    top_mod = modname

                # don't scan modules that aren't enabled
                if not enabled_extension(top_mod):
                    context.log.debug('ignored "%s" module during ext scan' % top_mod)
                    continue

                current_loc = prefix + modname
                # import module
                mod = __import__(current_loc, fromlist='dummy')

                if ispkg:
                    # if it is another package, recursively call this function
                    current_prefix = current_loc + '.'
                    recursive_mod_path = _recursive_manager_init(
                        mod, prefix=current_prefix, top_mod=top_mod
                    )

                    # add the mod path the recursive function walked to current
                    new_mod_path[modname] = recursive_mod_path
                else:
                    # otherwise if it is a module walk the objects to find ObjectManagers
                    for obj in mod.__dict__.values():

                        # if it is a class defintion
                        if inspect.isclass(obj):
                            # and it is a subclass of ObjectManager (but not
                            # ObjectManager itself)
                            if (issubclass(obj, ExtObjectManager) and
                                    obj.__name__ not in ExtObjectManager.__name__):
                                # add to object_managers
                                self.object_managers[obj.type] = obj()
                                self.external_object_manager_types.append(obj.type)
                                context.log.debug('loaded "%s" object manager from %s' % (obj.type, obj))

                            # or it is a subclass of AbstractManager (but not
                            # AbstractManager itself or an ObjectManager)
                            elif (issubclass(obj, AbstractExtManager) and
                                  obj.__name__ not in (AbstractExtManager.__name__,
                                                       ExtObjectManager.__name__)):
                                # add to external_managers
                                self.external_managers[obj.name] = obj
                                context.log.debug('loaded "%s" manager from %s' % (obj.name, obj))

                            # or it is a subclass of AbstractConfig (but not
                            # AbstractConfig itself)
                            elif (issubclass(obj, AbstractExtConfig) and
                                  obj.__name__ != AbstractExtConfig.__name__):
                                # check that the extension is enabled in the config
                                # add to ConfigTank
                                config = obj()
                                context.app_config.add(config)
                                context.log.debug('loaded "%s" extension config from %s' % (obj.ext, obj))

                # add now completed modpath walk to return
                module_paths.update(new_mod_path)

            return module_paths

        # start the recursive loading process...
        _recursive_manager_init(extensions)

    def run(self):
        # get correct pid
        context.set_pid()

        # set thread name
        current_thread().name = 'supervisor'

        # get initial config from cloud
        self.talk_to_cloud(initial=True)

        # init object managers
        self.init_object_managers()

        # load ext managers
        self.load_ext_managers()

        if not self.object_managers:
            context.log.error('no object managers configured, stopping')
            return

        # run bridge manager
        self.bridge_object = Bridge()
        self.bridge = spawn(self.bridge_object.start)

        # register exit handlers
        atexit.register(self.stop_everything)
        atexit.register(self.bridge_object.flush_metrics)

        # main cycle
        while True:
            time.sleep(5.0)

            # stop if was running in debug mode for more than five minutes
            if self.debug_mode:
                elapsed_time = int(time.time()) - self.start_time
                if elapsed_time > self.debug_mode_time:
                    self.stop()
                else:
                    print("Agent is running in debug mode, %s seconds to go..." % (self.debug_mode_time - elapsed_time))

            if not self.is_running:
                break

            try:
                context.inc_action_id()

                # run internal object managers
                for object_manager_name in self.object_manager_order:
                    object_manager = self.object_managers[object_manager_name]
                    object_manager.run()

                # run external object managers
                external_object_managers = filter(lambda x: x not in self.object_manager_order, self.object_managers.keys())
                for object_manager_name in external_object_managers:
                    object_manager = self.object_managers[object_manager_name]
                    object_manager.run()

                # manage external regular managers
                self.manage_external_managers()

                # talk to cloud
                try:
                    if context.objects.root_object:
                        if context.objects.root_object.definition and context.objects.root_object.definition_healthy:
                            context.inc_action_id()
                            self.talk_to_cloud(root_object=context.objects.root_object.definition)
                        else:
                            context.log.error('Problem with root object definition, agent stopping')
                            self.stop()
                    else:
                        pass
                        # context.default_log.debug('No root object defined during supervisor main run')
                except AmplifyCriticalException:
                    pass

                self.check_bridge()
            except OSError as e:
                if e.errno == 12:  # OSError errno 12 is a memory error (unable to allocate, out of memory, etc.)
                    context.log.error('OSError: [Errno %s] %s' % (e.errno, e.message), exc_info=True)
                    continue
                else:
                    raise e

    def stop(self):
        """
        Dummy for python daemon
        """
        self.is_running = False

    def stop_everything(self):
        """
        Stops all managers, collectors, etc
        :return:
        """
        # stop internal managers
        for object_manager_name in reversed(self.object_manager_order):
            object_manager = self.object_managers[object_manager_name]
            object_manager.stop()

        # stop other managers
        ext_managers = filter(
            lambda name: name not in self.object_manager_order,
            self.object_managers.keys()
        )
        for object_manager_name in ext_managers:
            object_manager = self.object_managers[object_manager_name]
            object_manager.stop()

        # log agent stopped event
        context.log.info(
            'agent stopped, version=%s pid=%s uuid=%s' %
            (context.version, context.pid, context.uuid)
        )

    def talk_to_cloud(self, root_object=None, force=False, initial=False):
        """
        Asks cloud for config, object configs, filters, etc
        Applies gathered data to objects and agent config

        :param root_object: {} definition dict of a top object
        :param force: bool will skip time check
        :param initial: bool first run
        """
        now = int(time.time())
        if not force and (
            now <= (
                self.last_cloud_talk_time +
                context.app_config['cloud']['talk_interval'] +
                self.cloud_talk_delay
            ) or
            now < context.backpressure_time
        ):
            return

        # Handle root_object before explicitly initializing a root object
        if not root_object:
            root_object = get_root_definition()

        # talk to cloud
        try:
            # reset the cloud talk counter to avoid sending new requests every 5.0 seconds
            self.last_cloud_talk_time = int(time.time())

            cloud_response = CloudResponse(
                context.http_client.post('agent/', data=root_object)
            )

            if self.cloud_talk_delay:
                self.cloud_talk_fails = 0
                self.cloud_talk_delay = 0
                context.log.debug('successful cloud connect, reset cloud talk delay')
        except Exception as e:
            if isinstance(e, HTTPError) and e.response.status_code == 503:
                backpressure_error = HTTP503Error(e)
                context.backpressure_time = int(time.time() + backpressure_error.delay)
                context.log.debug(
                    'back pressure delay %s added (next talk: %s)' % (
                        backpressure_error.delay,
                        context.backpressure_time
                    )
                )
            else:
                self.cloud_talk_fails += 1
                self.cloud_talk_delay = exponential_delay(self.cloud_talk_fails)
                context.log.debug(
                    'cloud talk delay set to %s (fails: %s)' % (self.cloud_talk_delay, self.cloud_talk_fails)
                )

            context.log.error('could not connect to cloud', exc_info=True)
            raise AmplifyCriticalException()

        # check agent version status
        if context.version_semver <= cloud_response.versions.obsolete:
            context.log.error(
                'agent is obsolete - cloud will refuse updates until it is updated (version: %s, current: %s)' %
                (tuple_to_version(context.version_semver), tuple_to_version(cloud_response.versions.current))
            )
            self.stop()
        elif context.version_semver <= cloud_response.versions.old:
            context.log.warn(
                'agent is old - update is recommended (version: %s, current: %s)' %
                (tuple_to_version(context.version_semver), tuple_to_version(cloud_response.versions.current))
            )

        # set capabilities
        for name, status in cloud_response.capabilities.items():
            name = ''.join([char.lower() for char in name if char.isalpha()])
            context.capabilities[name] = status

        # update special object configs and filters
        changed_object_managers = set()
        matched_object_configs = set()
        for obj in cloud_response.objects:
            object_manager = self.object_managers.get(obj.type)
            if object_manager is None:
                continue

            if obj.id in object_manager.object_configs:
                matched_object_configs.add(obj.id)

            if object_manager.object_configs.get(obj.id, {}) != obj.config:
                context.log.info(
                    'object config has changed. now "%s" %s is running with: %s' %
                    (obj.type, obj.id, pprint.pformat(obj.config))
                )
                object_manager.object_configs[obj.id] = obj.config
                changed_object_managers.add(obj.type)
                matched_object_configs.add(obj.id)

        # purge obsoleted object configs
        for object_type, object_manager in self.object_managers.items():
            for obj_id in object_manager.object_configs.keys():
                if obj_id not in matched_object_configs:
                    context.log.debug(
                        'object config has changed. now "%s" %s is running with default settings' %
                        (object_type, obj_id)
                    )
                    del object_manager.object_configs[obj_id]
                    changed_object_managers.add(object_type)

        # don't change api_url if a custom url was set by the user in the agent config
        if context.freeze_api_url:
            cloud_response.config.get('cloud', {}).pop('api_url', None)

        # global config changes
        def _recursive_dict_match_only_existing(kwargs1, kwargs2):
            for k, v1 in kwargs1.items():
                if isinstance(v1, dict):
                    v2 = kwargs2.get(k, {})

                    if not isinstance(v2, dict):
                        return False

                    if not _recursive_dict_match_only_existing(
                            v1, kwargs2.get(k, {})
                    ):
                        return False
                else:
                    if v1 != kwargs2.get(str(k)):
                        return False
            return True

        config_changed = not _recursive_dict_match_only_existing(
            cloud_response.config, context.app_config.default
        )

        # apply new config
        context.app_config.apply(cloud_response.config, target=0)

        # perform restarts
        if config_changed or len(changed_object_managers) > 0:
            context.cloud_restart = True
            if self.bridge_object:
                self.bridge_object.flush_metrics()

            if config_changed:
                context.log.debug(
                    'app config has changed. now running with: %s' %
                    pprint.pformat(context.app_config.config)
                )

                context.http_client.update_cloud_url()

                if self.object_managers:
                    for object_manager_name in reversed(self.object_manager_order):
                        object_manager = self.object_managers[object_manager_name]
                        object_manager.stop()

                    for object_manager_name in self.external_object_manager_types:
                        object_manager = self.object_managers[object_manager_name]
                        object_manager.stop()

                    for name in self.external_managers.keys():
                        attr_string = '%s_manager' % name
                        thread = getattr(self, attr_string, None)
                        if thread is not None:
                            thread.kill()

            elif len(changed_object_managers) > 0:
                context.log.debug(
                    'obj configs changed. changed managers: %s' % list(changed_object_managers)
                )
                for obj_type in changed_object_managers:
                    self.object_managers[obj_type].stop()

            if not initial:
                self.init_object_managers()
                self.load_ext_managers()

            self.last_cloud_talk_restart = int(time.time())
            context.cloud_restart = False

    def check_bridge(self):
        """
        Check containers threads, restart if some failed
        """
        if self.bridge.ready and self.bridge.exception:
            context.log.debug('bridge exception: %s' % self.bridge.exception)
            self.bridge = gevent.spawn(Bridge().start)

    def manage_external_managers(self):
        """
        Check external managers, start/restart them if needed
        """
        for name, manager_cls in self.external_managers.items():
            attr_string = '%s_manager' % name
            thread = getattr(self, attr_string, None)

            if thread is None:
                # start and set the manager
                context.log.debug(
                    'starting "%s" external manager' % manager_cls.__name__
                )
                setattr(self, attr_string, gevent.spawn(manager_cls().start))
            elif thread.dead:
                # manager was stopped (or thread killed)
                context.log.debug(
                    'starting "%s" external manager after stop' % manager_cls.__name__
                )
                setattr(self, attr_string, gevent.spawn(manager_cls().start))
            elif thread.ready and thread.exception:
                context.log.debug(
                    'restarting "%s" external manager' % manager_cls.__name__
                )
                # restart crashed managers
                setattr(self, attr_string, gevent.spawn(manager_cls().start))
