# -*- coding: utf-8 -*-
import time

from amplify.agent.collectors.abstract import AbstractCollector
from amplify.agent.common.context import context
from amplify.agent.data.eventd import CRITICAL, INFO, WARNING

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"

MAX_SIZE_FOR_TEST = 20 * 1024 * 1024  # 20 MB
DEFAULT_PARSE_DELAY = 60.0


class NginxConfigCollector(AbstractCollector):
    short_name = 'nginx_config'

    def __init__(self, previous=None, **kwargs):
        super(NginxConfigCollector, self).__init__(**kwargs)

        self.previous = previous or {
            'files': {},
            'directories': {}
        }

        self.parse_delay = context.app_config['containers'].get('nginx', {}).get('parse_delay', DEFAULT_PARSE_DELAY)

        self.register(
            self.parse_config
        )

    def parse_config(self, no_delay=False):
        """
        Parses the NGINX configuration file.

        Will not run if:
            a) it hasn't been long enough since the last time it parsed (unless `no_delay` is True)
            b) the configuration files from the last parse haven't changed

        :param no_delay: bool - ignore delay times for this run (useful for testing)
        """
        config = self.object.config

        # don't parse config if it hasn't been long enough since last parse
        if not no_delay and time.time() < config.wait_until:
            return

        files, directories = config.collect_structure(include_ssl_certs=self.object.upload_ssl)

        # only parse config if config files have changed since last collect
        if files == self.previous['files']:
            return

        self.previous['files'] = files
        self.previous['directories'] = directories

        # parse config tree
        start_time = time.time()
        try:
            config.full_parse(include_ssl_certs=self.object.upload_ssl)
        finally:
            elapsed_time = time.time() - start_time
            delay = 0 if no_delay else max(elapsed_time * 2, self.parse_delay)
            config.wait_until = start_time + delay

        # Send event for parsing nginx config.
        # Use config.parser.filename to account for default value defined in NginxConfigParser.
        self.object.eventd.event(
            level=INFO,
            message='nginx config parsed, read from %s' % config.filename,
        )
        for error in config.parser_errors:
            self.object.eventd.event(level=WARNING, message=error)

        # run ssl checks
        config.run_ssl_analysis()

        # run upload
        if self.object.upload_config:
            checksum = config.checksum()
            self.upload(config, checksum)

        # otherwise run test
        if self.object.run_config_test and config.total_size() < MAX_SIZE_FOR_TEST:
            run_time = config.run_test()

            # send event for testing nginx config
            if config.test_errors:
                self.object.eventd.event(level=WARNING, message='nginx config test failed')
            else:
                self.object.eventd.event(level=INFO, message='nginx config tested ok')

            for error in config.test_errors:
                self.object.eventd.event(level=CRITICAL, message=error)

            # stop -t if it took too long
            if run_time > context.app_config['containers']['nginx']['max_test_duration']:
                context.app_config['containers']['nginx']['run_test'] = False
                context.app_config.mark_unchangeable('run_test')
                self.object.eventd.event(
                    level=WARNING,
                    message='%s -t -c %s took %s seconds, disabled until agent restart' % (
                        config.binary, config.filename, run_time
                    )
                )
                self.object.run_config_test = False

    def handle_exception(self, method, exception):
        super(NginxConfigCollector, self).handle_exception(method, exception)
        self.object.eventd.event(
            level=INFO,
            message='nginx config parser failed, path %s' % self.object.conf_path,
            onetime=True
        )

    def upload(self, config, checksum):
        payload = {
            'tree': config.tree,
            'directory_map': config.directory_map,
            'files': config.files,
            'directories': config.directories,
            'ssl_certificates': config.ssl_certificates,
            'access_logs': config.access_logs,
            'error_logs': config.error_logs,
            'errors': {
                'parser': len(config.parser_errors),
                'test': len(config.test_errors)
            }
        }
        self.object.configd.config(payload=payload, checksum=checksum)
