# -*- coding: utf-8 -*-
import time

from amplify.agent.collectors.nginx.accesslog import NginxAccessLogsCollector
from amplify.agent.collectors.nginx.config import NginxConfigCollector
from amplify.agent.collectors.nginx.errorlog import NginxErrorLogsCollector

from amplify.agent.common.context import context
from amplify.agent.common.util import http, net, plus
from amplify.agent.data.eventd import INFO, WARNING
from amplify.agent.objects.abstract import AbstractObject
from amplify.agent.objects.nginx.binary import nginx_v
from amplify.agent.objects.nginx.filters import Filter
from amplify.agent.pipelines.syslog import SyslogTail
from amplify.agent.pipelines.file import FileTail


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class NginxObject(AbstractObject):
    type = 'nginx'

    def __init__(self, **kwargs):
        super(NginxObject, self).__init__(**kwargs)

        # Have to override intervals here because new container sub objects.
        self.intervals = context.app_config['containers'].get('nginx', {}).get('poll_intervals', {'default': 10})

        self.root_uuid = context.uuid
        self._local_id = self.data['local_id']  # Assigned by manager
        self.pid = self.data['pid']
        self.version = self.data['version']
        self.workers = self.data['workers']
        self.prefix = self.data['prefix']
        self.bin_path = self.data['bin_path']
        self.conf_path = self.data['conf_path']
        self.name = self.version

        # agent config
        default_config = context.app_config['containers']['nginx']
        self.upload_config = self.data.get('upload_config') or default_config.get('upload_config', False)
        self.run_config_test = self.data.get('run_test') or default_config.get('run_test', False)
        self.upload_ssl = self.data.get('upload_ssl') or default_config.get('upload_ssl', False)

        # nginx -V data
        self.parsed_v = nginx_v(self.bin_path)

        # filters
        self.filters = [Filter(**raw_filter) for raw_filter in self.data.get('filters') or []]

        # nginx config
        if 'config_data' in self.data:
            self._restore_config_collector(self.data['config_data']['previous'])
        else:
            self._setup_config_collector()

        # api
        self.api_endpoints_to_skip = self.get_api_endpoints_to_skip()
        self.api_external_url, self.api_internal_url = self.get_alive_api_urls()
        self.api_enabled = True if (self.api_external_url or self.api_internal_url) else False
        api_url = self.api_internal_url if self.api_internal_url is not None else self.api_external_url
        if self.api_enabled and plus.get_latest_supported_api(api_url) is None:
            context.log.debug("API directive was specified but no supported API was found.")
            self.api_enabled = False

        # plus status
        self.plus_status_external_url, self.plus_status_internal_url = self.get_alive_plus_status_urls()
        self.plus_status_enabled = True if (self.plus_status_external_url or self.plus_status_internal_url) else False

        # stub status
        self.stub_status_url = self.get_alive_stub_status_url()
        self.stub_status_enabled = True if self.stub_status_url else False

        self.processes = []

        self.reloads = self.data.get('reloads', 0)

        self._setup_meta_collector()
        self._setup_metrics_collector()
        self._setup_access_logs()
        self._setup_error_logs()

        # publish events for old object
        for error in self.config.parser_errors:
            self.eventd.event(level=WARNING, message=error)

    @property
    def status_directive_supported(self):
        release = self.parsed_v['plus']['release']
        if release is not None:
            if release.startswith('nginx-plus-r'):
                r = release.split('-')[2].lstrip('r')
                if r.isdigit():
                    if int(r) <= 15:
                        return True
        return False

    @property
    def definition(self):
        # Type is hard coded so it is not different from ContainerNginxObject.
        return {'type': 'nginx', 'local_id': self.local_id, 'root_uuid': self.root_uuid}

    @property
    def config(self):
        return context.nginx_configs[(self.conf_path, self.prefix, self.bin_path)]

    def get_api_endpoints_to_skip(self):
        """
        Searches main context for http and stream blocks and returns which ones were not found.
        """
        to_find = set(['http', 'stream'])
        main_ctx = set(stmt['directive'] for stmt in self.config.subtree)
        return list(to_find - main_ctx)

    def get_alive_stub_status_url(self):
        """
        Tries to get alive stub_status url
        Records some events about it

        :return: str stub_status url
        """
        urls_to_check = self.config.stub_status_urls

        if 'stub_status' in context.app_config.get('nginx', {}):
            predefined_uri = context.app_config['nginx']['stub_status']
            urls_to_check.append(http.resolve_uri(predefined_uri))

        stub_status_url = self.__get_alive_status(urls_to_check, what='stub status')
        if stub_status_url:
            # Send stub detected event
            self.eventd.event(
                level=INFO,
                message='nginx stub_status detected, %s' % stub_status_url
            )
        else:
            self.eventd.event(
                level=INFO,
                message='nginx stub_status not found in nginx config'
            )
        return stub_status_url

    def get_alive_plus_status_urls(self):
        """
        Tries to get alive plus urls
        There are two types of plus status urls: internal and external
        - internal are for the agent and usually they have the localhost ip in address
        - external are for the browsers and usually they have a normal server name

        Returns a tuple of str or Nones - (external_url, internal_url)

        Even if external status url is not responding (cannot be accesible from the host)
        we should return it to show in our UI

        :return: (str or None, str or None)
        """
        internal_urls = self.config.plus_status_internal_urls
        external_urls = self.config.plus_status_external_urls

        if 'plus_status' in context.app_config.get('nginx', {}):
            predefined_uri = context.app_config['nginx']['plus_status']
            internal_urls.append(http.resolve_uri(predefined_uri))

        internal_status_url = self.__get_alive_status(internal_urls, json=True, what='plus status internal')
        if internal_status_url:
            self.eventd.event(
                level=INFO,
                message='nginx internal plus_status detected, %s' % internal_status_url
            )

        external_status_url = self.__get_alive_status(external_urls, json=True, what='plus status external')
        if len(self.config.plus_status_external_urls) > 0:
            if not external_status_url:
                external_status_url = self.config.plus_status_external_urls[0]

            self.eventd.event(
                level=INFO,
                message='nginx external plus_status detected, %s' % external_status_url
            )

        return external_status_url, internal_status_url

    def get_alive_api_urls(self):
        """
        Tries to get alive api urls
        There are two types of api urls: internal and external
        - internal are for the agent and usually they have the localhost ip in address
        - external are for the browsers and usually they have a normal server name

        Returns a tuple of str or Nones - (external_url, internal_url)

        Even if external api url is not responding (cannot be accesible from the host)
        we should return it to show in our UI

        :return: (str or None, str or None)
        """
        internal_urls = self.config.api_internal_urls
        external_urls = self.config.api_external_urls

        if 'api' in context.app_config.get('nginx', {}):
            predefined_uri = context.app_config['nginx']['api']
            internal_urls.append(http.resolve_uri(predefined_uri))

        internal_api_url = self.__get_alive_status(internal_urls, json=True, what='api internal')
        if internal_api_url:
            self.eventd.event(
                level=INFO,
                message='nginx internal api detected, %s' % internal_api_url
            )

        external_api_url = self.__get_alive_status(external_urls, json=True, what='api external')
        if len(self.config.api_external_urls) > 0:
            if not external_api_url:
                external_api_url = self.config.api_external_urls[0]

            self.eventd.event(
                level=INFO,
                message='nginx external api detected, %s' % external_api_url
            )

        return external_api_url, internal_api_url

    def __get_alive_status(self, url_list, json=False, what='api/stub status/plus status'):
        """
        Tries to find alive status url
        Returns first alive url or None if all founded urls are not responding

        :param url_list: [] of urls
        :param json: bool - will try to encode json if True
        :param what: str - what kind of url (used for logging)
        :return: None or str
        """
        for url in url_list:
            if url.startswith('http://'):
                full_urls = [url, 'https://'+url[7:]]
            elif url.startswith('https://'):
                full_urls = [url, 'http://'+url[8:]]
            else:
                full_urls = ['http://'+url, 'https://'+url]

            for full_url in full_urls:
                try:
                    status_response = context.http_client.get(full_url, timeout=0.5, json=json, log=False)
                    if status_response:
                        if json or 'Active connections' in status_response:
                            return full_url
                    else:
                        context.log.debug('bad response from %s url %s' % (what, full_url))
                except:
                    context.log.debug('bad response from %s url %s' % (what, full_url))
        return None

    def __setup_pipeline(self, name):
        """
        Sets up a pipeline/tail object for a collector based on "filename".

        :param name: Str
        :return: Pipeline
        """
        tail = None
        try:
            if name.startswith('syslog'):
                address_bucket = name.split(',', 1)[0]
                host, port, address = net.ipv4_address(
                    address=address_bucket.split('=')[1], full_format=True, silent=True
                )
                # Right now we assume AFNET address/port...e.g. no support for unix sockets

                if address in context.listeners:
                    port = int(port)  # socket requires integer port
                    tail = SyslogTail(address=(host, port))
            else:
                tail = FileTail(name)
        except Exception as e:
            context.log.error(
                'failed to initialize pipeline for "%s" due to %s (maybe has no rights?)' % (name, e.__class__.__name__)
            )
            context.log.debug('additional info:', exc_info=True)

        return tail

    def _setup_meta_collector(self):
        collector_cls = self._import_collector_class('nginx', 'meta')
        self.collectors.append(
            collector_cls(object=self, interval=self.intervals['meta'])
        )

    def _setup_metrics_collector(self):
        collector_cls = self._import_collector_class('nginx', 'metrics')
        self.collectors.append(
            collector_cls(object=self, interval=self.intervals['metrics'])
        )

    def _setup_config_collector(self):
        collector = NginxConfigCollector(object=self, interval=self.intervals['configs'])
        try:
            start_time = time.time()
            collector.collect()  # run parse on startup
        finally:
            end_time = time.time()
            context.log.debug(
                '%s config parse on startup in %.3f' % (self.definition_hash, end_time - start_time)
            )
        self.collectors.append(collector)

    def _restore_config_collector(self, previous):
        collector = NginxConfigCollector(object=self, interval=self.intervals['configs'], previous=previous)
        try:
            start_time = time.time()
            collector.collect(no_delay=True)  # run NginxConfigCollector.parse_config on object restart
        finally:
            end_time = time.time()
            context.log.debug(
                '%s restored previous config collector in %.3f' % (self.definition_hash, end_time - start_time)
            )
        self.collectors.append(collector)

    def _setup_access_logs(self):
        # access logs
        for log_description, log_data in self.config.access_logs.items():
            format_name = log_data['log_format']
            log_format = self.config.log_formats.get(format_name)
            tail = self.__setup_pipeline(log_description)

            if tail:
                self.collectors.append(
                    NginxAccessLogsCollector(
                        object=self,
                        interval=self.intervals['logs'],
                        log_format=log_format,
                        tail=tail
                    )
                )

                # Send access log discovery event.
                self.eventd.event(level=INFO, message='nginx access log %s found' % log_description)

    def _setup_error_logs(self):
        # error logs
        for log_description, log_data in self.config.error_logs.items():
            log_level = log_data['log_level']
            tail = self.__setup_pipeline(log_description)

            if tail:
                self.collectors.append(
                    NginxErrorLogsCollector(
                        object=self,
                        interval=self.intervals['logs'],
                        level=log_level,
                        tail=tail
                    )
                )

                # Send error log discovery event.
                self.eventd.event(level=INFO, message='nginx error log %s found' % log_description)


class ContainerNginxObject(NginxObject):
    type = 'container_nginx'
