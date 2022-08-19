# -*- coding: utf-8 -*-
import os
import pwd
import time
import traceback

import requests

from amplify.agent.common.context import context
from amplify.agent.common.util.loader import import_class

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"

CONFIG_CACHE = {}


def read(config_name, config_file=None):
    """
    Reads specified config and caches it in CONFIG_CACHE dict

    Each config is a python file which can
    Typical name of config for example: /agent/config/app.py

    :param config_name: str config name
    :param config_file: str config file name
    :return: python object
    """
    if config_name not in CONFIG_CACHE:
        full_module_name = 'amplify.agent.common.config.%s' % config_name
        class_name = '%sConfig' % context.environment.title()
        config_object = import_class('%s.%s' % (full_module_name, class_name))(config_file)
        CONFIG_CACHE[config_name] = config_object

    return CONFIG_CACHE[config_name]


def test(config_filename, pid_file, wait_for_cloud, agent_name):
    """
    Checks important parameters and checks connection to the cloud

    :param config_filename: str config file
    :param pid_file: str pid file
    :param wait_for_cloud: bool - if True the agent will try to connect to the Cloud once again
    :param agent_name
    :return: int: 0 if everything is ok, 1 if something is wrong
    """
    print('')

    try:
        # check that config file exists
        if not os.path.isfile(config_filename) or not os.access(config_filename, os.R_OK):
            print("\033[31mConfig file %s could not be found or opened.\033[0m\n" % config_filename)
            print("If you installed the agent from the package you should do the following actions:")
            print("  1. sudo cp %s.default %s" % (config_filename, config_filename))
            print("  2. sudo chown nginx %s" % config_filename)
            print("  3. write your API key in [credentials][api_key]")
            return 1

        # check it can be loaded
        try:
            from amplify.agent.common.context import context
            context.setup(
                app='agent',
                agent_name=agent_name,
                config_file=config_filename,
                pid_file=pid_file,
                skip_uuid=True
            )
        except IOError as e:
            if hasattr(e, 'filename'):  # log error
                pass
            else:
                raise e

        # check that it has API url
        if not context.app_config['cloud']['api_url']:
            if agent_name == 'amplify':
                api_url = 'https://receiver.amplify.nginx.com:443/1.4'
            else:
                api_url = 'https://FQDN-OF-YOUR-INSTALLATION:8443/1.4'
            print("\033[31mAPI url is not specified in %s\033[0m\n" % config_filename)
            print("Write API url %s in [cloud][api_url]" % api_url)
            return 1

        # check that is has API key
        if not context.app_config['credentials']['api_key']:
            print("\033[31mAPI key is not specified in %s\033[0m\n" % config_filename)
            print("Write your API key in [credentials][api_key]")
            return 1

        # test logger: get log filename first
        try:
            log_filename = context.default_log.handlers[0].baseFilename
            log_folder = '/'.join(log_filename.split('/')[:-1])
        except:
            print("\033[31mCould not setup log file based on config in %s\033[0m\n" % config_filename)
            print("Please check the file name in [handler_agent-default][args]")
            return 1

        # test logger: the ability to write logs
        try:
            context.log.info('performing configtest check...')
        except:
            current_user = pwd.getpwuid(os.getuid())[0]
            print("\033[31mCould not write to %s\033[0m\n" % log_filename)
            print("Either wrong permissions, or the log directory doesn't exist\n")
            print("The following may help:")
            print("  1. sudo mkdir %s" % log_folder)
            print("  2. sudo touch %s" % log_filename)
            print("  3. sudo chown %s %s" % (current_user, log_filename))
            return 1

        # try to connect to the cloud
        tries = 0
        while tries <= 3:
            tries += 1

            try:
                context.http_client.post('agent/', {})
            except (requests.HTTPError, requests.ConnectionError) as e:
                api_url = context.app_config['cloud']['api_url']
                print("\033[31mCould not connect to API via url %s\033[0m\n" % api_url)

                if e.response and e.response.status_code == 404:
                    api_key = context.app_config['credentials']['api_key']
                    print("\033[31mIt seems like your API key '%s' is wrong. \033[0m\n" % api_key)
                    return 1
                else:
                    if (wait_for_cloud and tries == 1) or wait_for_cloud is False:
                        print("\033[31mIt seems like we have little problems connecting to API.\033[0m")
                        print("\033[31mApologies and bear with us. \033[0m\n")

                    if wait_for_cloud and tries < 3:
                        print("\033[31mWe will try to establish a connection once again in a minute.\033[0m\n")

                if wait_for_cloud and tries == 3:
                    print("\033[31mGiving up after three attempts...\033[0m\n")
                    return 1
                elif wait_for_cloud is False:
                    return 1
                else:
                    time.sleep(60)
            else:
                break
    except:
        print("\033[31mSomething failed:\033[0m\n")
        print(traceback.format_exc())
        return 1

    context.log.info('config file is ok!')
    print("\033[32mConfig file %s is OK\033[0m" % config_filename)
    return 0
