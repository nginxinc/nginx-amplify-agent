# -*- coding: utf-8 -*-
import ast
import os
import sys
import time

from threading import current_thread
from collections import defaultdict

from amplify.agent import Singleton
from amplify.agent.common.util.ps import Process
from amplify.agent.common.util.cycle import cycle

try:
    import thread
except ImportError:
    # Renamed in Python 3
    import _thread as thread


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"

sys.tracebacklimit = 10000
sys.setrecursionlimit(2048)


class Context(Singleton):
    def __init__(self):
        # initial basics
        self.pid = None
        self.psutil_process = None
        self.set_pid()

        # define vars
        self.cpu_last_check = 0
        self.version_semver = (1, 8, 2)
        self.version_build = 1
        self.uuid = None
        self.version = '%s-%s' % ('.'.join(map(str, self.version_semver)), self.version_build)
        self.environment = None
        self.imagename = None
        self.container_type = None
        self.http_client = None
        self.default_log = None
        self.app_name = None
        self.app_config = None
        self.listeners = None
        self.tags = []
        self.ids = {}
        self.action_ids = {}
        self.cloud_restart = False  # Handle improper duplicate logging of start/stop events.
        self.freeze_api_url = False
        self.agent_name = ''
        self.capabilities = defaultdict(bool)

        self.objects = None
        self.top_object = None  # TODO: Remove top_object entirely in favor of just top_object_id.
        self.top_object_id = None  # TODO: Think about refactoring such that top_object_id unnecessary.
        self.plus_cache = None
        self.nginx_configs = None

        self.start_time = int(time.time())
        self.backpressure_time = 0

        # ring 0 thread_id set up and protect
        self.setup_thread_id()
        self.supervisor_thread_id = list(self.ids.keys())[0]

        self.setup_environment()

    def set_pid(self):
        self.pid = os.getpid()
        self.psutil_process = Process(self.pid)

    def setup_environment(self):
        """
        Setup common environment vars
        """
        self.environment = os.environ.get('AMPLIFY_ENVIRONMENT', 'production')
        self.imagename = os.environ.get('AMPLIFY_IMAGENAME')

    def setup(self, **kwargs):
        self._setup_app_config(**kwargs)
        self._setup_app_logs(**kwargs)
        self._setup_app_listeners()
        self._setup_tags()
        # we don't need to work with host details on config check for example
        if not kwargs.get('skip_uuid', False):
            self._setup_host_details()
        self._setup_http_client()
        self._setup_object_tank()
        self._setup_plus_cache()
        self._setup_nginx_config_tank()
        self._setup_container_details()

    def _setup_app_config(self, **kwargs):
        self.app_name = kwargs.get('app')
        app_config = kwargs.get('app_config')

        from amplify.agent.common.util import configreader
        if app_config is None:
            app_config = configreader.read('app', config_file=kwargs.get('config_file'))
        else:
            configreader.CONFIG_CACHE['app'] = app_config

        if self.app_config is not None:
            self.app_config = None

        from amplify.agent.tanks.config import ConfigTank
        config_tank = ConfigTank()
        config_tank.add(app_config)
        self.app_config = config_tank

        # if the api_url was set in the config and isn't from our receiver's domain then never overwrite it
        api_url = self.app_config.get('cloud', {}).get('api_url', '') or ''
        from_saas = api_url.startswith('https://receiver.amplify.nginx.com')
        self.freeze_api_url = bool(api_url) and not from_saas

        if kwargs.get('pid_file'):  # If pid_file given in setup, then assume agent running in daemon mode.
            self.app_config['daemon']['pid'] = kwargs.get('pid_file')
            # This means 'daemon' in self.app_config.keys() is a reasonable test for detecting whether agent is running
            # as a daemon or in the foreground (or generically using self.app_config.get('daemon') which will return
            # None if running in foreground).

        # If an image name is not specified, but there is an AMPLIFY_IMAGENAME environment variable, set the config
        # value to the environment value.  This means that config file will always take precedence.  This also means
        # that the app_config is the source of truth for our program logic when trying to determine imagename/whether or
        # not in a container.
        if not self.app_config['credentials']['imagename'] and self.imagename:
            self.app_config['credentials']['imagename'] = self.imagename

        # if in a container, sets self.uuid to a... not... ultimately unique id that's based on the imagename
        if self.app_config['credentials']['imagename']:
            self.app_config['credentials']['uuid'] = 'container-%s' % self.app_config['credentials']['imagename']

        self.agent_name = kwargs.get('agent_name')

    def _setup_app_logs(self, **kwargs):
        """
        Setup app log file

        :param log_file: str override the default log file
        :param debug: bool force debug log if True
        """
        log_file = kwargs.get('log_file')
        debug_mode = kwargs.get('debug')

        from amplify.agent.common.util import logger
        logger.setup(self.app_config.filename)
        self.default_log = logger.get('%s-default' % self.app_name)

        if log_file:
            for handler in self.default_log.handlers:
                self.default_log.removeHandler(handler)
            self.default_log.addHandler(logger.get_debug_handler(log_file))

        if debug_mode:
            self.default_log.setLevel(logger.logging.DEBUG)

    def _setup_app_listeners(self):
        from amplify.agent.common.util import net
        self.listeners = set()

        # get a list of listener names
        names = self.app_config.get('listeners', {}).get('keys', '').split(',')

        # for each listener...
        for name in names:
            # ...try to find the definition...
            listener_definition = self.app_config.get('listener_%s' % name)
            # ...if there is a definition...
            if listener_definition:
                # ...try to find the address...
                listener_address = listener_definition.get('address')
                # ...if there is an address...
                if listener_address is not None:
                    # ...try to format and save the ipv4 address into the context store.
                    try:
                        _, _, formatted_address = net.ipv4_address(address=listener_address, full_format=True)
                        self.listeners.add(formatted_address)
                    except:
                        pass  # just ignore bad ipv4 definitions for now

    def _setup_tags(self):
        # get the tags line from the tags section of the app config
        line = self.app_config.get('tags', {}).get('tags', '')
        try:
            # first try to parse tags assuming they're using the standard python syntax
            tags = ast.literal_eval(line)
        except:
            # if literal eval didn't work, assume they're using the unquoted comma-separated syntax
            tags = filter(len, map(str.strip, line.split(',')))

        # if 'tags' is a single quoted string, don't create a tag for each character
        if isinstance(tags, str):
            tags = [tags]

        self.tags = []
        for tag in tags:
            key, value = tag.split(':', 1) if ':' in tag else (None, tag)
            self.tags.append({'key': key, 'value': value})

    def _setup_host_details(self):
        from amplify.agent.common.util.host import hostname, uuid
        self.hostname = hostname()
        self.uuid = uuid()

        # only change agent config if uuid is generated and store_uuid == True
        if (context.app_config['credentials'].get('store_uuid', False) and
                context.app_config['credentials']['uuid'] == ''):
            context.app_config.save('credentials', 'uuid', context.uuid)

    def _setup_http_client(self):
        from amplify.agent.common.util.http import HTTPClient
        self.http_client = HTTPClient()

    def _setup_object_tank(self):
        from amplify.agent.tanks.objects import ObjectsTank
        self.objects = ObjectsTank()
        self.top_object = self.objects.root_object
        self.top_object_id = self.objects.root_id

    def _setup_plus_cache(self):
        from amplify.agent.tanks.plus_cache import PlusCache
        self.plus_cache = PlusCache()

    def _setup_nginx_config_tank(self):
        from amplify.agent.tanks.nginx_config import NginxConfigTank
        self.nginx_configs = NginxConfigTank()

    def _setup_container_details(self):
        from amplify.agent.common.util import container
        self.container_type = container.container_environment()

    def get_file_handlers(self):
        return [self.default_log.handlers[0].stream]

    def inc_action_id(self):
        thread_id = thread.get_ident()
        self.action_ids[thread_id] = '%s_%s' % (thread_id, self.ids[thread_id].next())

    def setup_thread_id(self):
        thread_id = thread.get_ident()
        self.ids[thread_id] = cycle(10000, 10000000)
        self.action_ids[thread_id] = '%s_%s' % (thread_id, self.ids[thread_id].next())

    def teardown_thread_id(self):
        thread_id = thread.get_ident()

        # if thread_id to teardown is supervisor itself, break
        if thread_id == self.supervisor_thread_id:
            self.log.debug(
                'skipping teardown of supervisor thread_id (id:%s, name:%s)' % (
                    self.supervisor_thread_id,
                    current_thread().name
                )
            )
            return

        try:
            del self.ids[thread_id]
        except KeyError:
            pass

        try:
            del self.action_ids[thread_id]
        except KeyError:
            pass

    @property
    def log(self):
        return self.default_log

    def check_and_limit_cpu_consumption(self):
        """
        Checks CPU consumption and if it's more than something performs time.sleep
        """
        try:
            now = time.time()
            cpu_limit = self.app_config['daemon']['cpu_limit']
            time_to_sleep = self.app_config['daemon']['cpu_sleep']

            if self.psutil_process and now > self.cpu_last_check + time_to_sleep/5:
                self.cpu_last_check = now
                user_percent, system_percent = self.psutil_process.cpu_percent()
                if user_percent >= cpu_limit:
                    self.default_log.debug(
                        'CPU usage is %s user, %s system, sleeping for %s s' %
                        (user_percent, system_percent, time_to_sleep)
                    )
                    time.sleep(time_to_sleep)
        except:
            self.default_log.debug('failed to check CPU usage', exc_info=True)


context = Context()
