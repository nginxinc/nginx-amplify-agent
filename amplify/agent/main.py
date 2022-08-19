# -*- coding: utf-8 -*-
import traceback
import sys

from optparse import OptionParser, Option

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx Inc. All rights reserved."
__credits__ = [
    "Mike Belov",
    "Andrew Alexeev",
    "Andrei Belov",
    "Oleg Mamontov",
    "Ivan Poluyanov",
    "Grant Hulegaard",
    "Arie van Luttikhuizen",
    "Igor Meleshchenko",
    "Eugene Morozov",
    "Jason Thigpen",
    "Alexander Shchukin",
    "Clayton Lowell",
    "Paul McGuire",
    "Raymond Lau",
    "Seth Malaki",
    "Luca Comellini",
    "Laura Greenbaum",
    "Abhimanyu Nagurkar",
    "Mani Lonkar",
    "Chez Ramalingam"
]
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


usage = "usage: %prog [start|stop|configtest] [options]"

option_list = (
    Option(
        '--config',
        action='store',
        dest='config',
        type='string',
        help='path to the config file',
        default=None,
    ),
    Option(
        '--pid',
        action='store',
        dest='pid',
        type='string',
        help='path to the pid file',
        default=None,
    ),
    Option(
        '--foreground',
        action='store_true',
        dest='foreground',
        help='do not daemonize, run in foreground',
        default=False,
    ),
    Option(
        '--log',
        action='store',
        dest='log',
        type='string',
        help='path to the log file',
        default=None,
    ),
)

parser = OptionParser(usage, option_list=option_list)
(options, args) = parser.parse_args()


def test_configuration_and_enviroment(*args):
    from amplify.agent.common.util import configreader
    return configreader.test(*args)


def run(agent_name=None):
    """
    Agent startup procedure
    Reads options, sets the environment, does other good things

    :param agent_name: str agent name
    """
    try:
        from setproctitle import setproctitle
        proctitle = '%s-agent' % agent_name
        setproctitle(proctitle)
    except ImportError:
        pass

    try:
        action = sys.argv[1]
        if action not in ('start', 'stop', 'configtest', 'debug'):
            raise IndexError
    except IndexError:
        print("Invalid action or no action supplied\n")
        parser.print_help()
        sys.exit(1)

    # check config before start
    if action in ('configtest', 'debug', 'start'):
        wait_for_cloud = True if action == 'start' else False

        rc = test_configuration_and_enviroment(
            options.config,
            options.pid,
            wait_for_cloud,
            agent_name
        )
        print("")

        if action == 'configtest' or rc:
            sys.exit(rc)

    # setup the context
    debug_mode = action == 'debug'
    try:
        from amplify.agent.common.context import context
        context.setup(
            app='agent',
            config_file=options.config,
            pid_file=options.pid,
            log_file=options.log,
            debug=debug_mode,
            agent_name=agent_name
        )
    except:
        traceback.print_exc()

    # run the agent
    try:
        from amplify.agent.supervisor import Supervisor
        supervisor = Supervisor(
            foreground=options.foreground,
            debug=debug_mode
        )

        if options.foreground or (debug_mode and options.log):
            supervisor.run()
        else:
            from amplify.agent.common.runner import Runner
            daemon_runner = Runner(supervisor)
            daemon_runner.do_action()
    except:
        context.default_log.error('uncaught exception during run time', exc_info=True)
        traceback.print_exc()
