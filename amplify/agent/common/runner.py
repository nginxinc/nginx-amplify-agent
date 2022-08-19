# -*- coding: utf-8 -*-
import signal

from daemon import runner

from amplify.agent.common.context import context

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class Runner(runner.DaemonRunner):
    def __init__(self, app):
        super(Runner, self).__init__(app)

        def cleanup(signum, frame):
            app.stop()

        self.app = app
        self.daemon_context.detach_process = True
        self.daemon_context.files_preserve = context.get_file_handlers()
        self.daemon_context.signal_map = {
            signal.SIGTERM: cleanup
        }

    def _open_streams_from_app_stream_paths(self, app):
        self.daemon_context.stdin = open(app.stdin_path, 'rt')
        self.daemon_context.stdout = open(app.stdout_path, 'w+t')
        self.daemon_context.stderr = open(app.stderr_path, 'w+t')
