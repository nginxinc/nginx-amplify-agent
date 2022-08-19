# -*- coding: utf-8 -*-
import abc
import time

from threading import current_thread

from amplify.agent.common.context import context


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Grant Hulegaard"
__email__ = "grant.hulegaard@nginx.com"


class AbstractExtRunner(object):
    """
    A runner is an encapsulated body that is spawned by a manager that should
    have a single lifecycle.  This differs from a Manager which is meant to
    indefenitely run in a loop until externaly stopped.
    """
    __slots__ = ('running', 'in_container')
    name = 'abstact_ext_runner'

    def __init__(self):
        self.running = False
        self.in_container = bool(context.app_config['credentials']['imagename'])

    @property
    def status(self):
        return 'running' if self.running else 'stopped'

    def _setup(self):
        """
        Special method that is run before self._run().  May be used by
        child objects to do work before main logic.

        Exceptions in this logic will prevent main logic from running.
        """
        pass

    @abc.abstractmethod
    def _run(self):
        # Example since this is an abstract method.
        try:
            pass  # Do something here...
        except:
            context.default_log.error('failed', exc_info=True)
            raise

    def _teardown(self):
        """
        Special method that is run after self._run().  May be used by
        child objects to do work after main logic.

        This logic is guaranteed to run even if main logic fails.

        Exceptions in this logic are unhandled by the runner.
        """
        pass

    def start(self):
        """
        Execution entry point.  Does some setup and then runs the _run routine.
        """
        # TODO: Standardize this with collectors and managers.
        current_thread().name = self.name
        context.setup_thread_id()

        self.running = True

        context.inc_action_id()
        start = time.time()
        try:
            self._setup()
            self._run()
        except Exception as e:
            context.default_log.error(
                '"%s" critical exception "%s" caught during run' % (
                    self.__class__.__name__,
                    e.__class__.__name__
                )
            )
            context.default_log.debug('additional info:', exc_info=True)
        finally:
            try:
                self._teardown()
            finally:
                end = time.time()
                context.default_log.debug(
                    '%s (%s) run complete in %0.2f' % (
                        self.__class__.__name__,
                        id(self),
                        end - start
                    )
                )

        self.stop()

    def stop(self):
        self.running = False
        context.teardown_thread_id()

    def __del__(self):
        """
        This is meant to catch situations where GC cleans up a routine that
        found itself in an invalid state.
        """
        if self.running:
            self.stop()
