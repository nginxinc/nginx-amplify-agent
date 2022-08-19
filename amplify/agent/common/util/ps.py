# -*- coding: utf-8 -*-
import time
import psutil
import sys

from amplify.agent.common.util import subp


__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class Process(psutil.Process):
    def cpu_percent(self, interval=None):
        """
        Rewrites original method to return two values (system and user) instead of one (overall)

        Return a float representing the current process CPU
        utilization as a percentage.

        When interval is 0.0 or None (default) compares process times
        to system CPU times elapsed since last call, returning
        immediately (non-blocking). That means that the first time
        this is called it will return a meaningful 0.0 value.

        When interval is > 0.0 compares process times to system CPU
        times elapsed before and after the interval (blocking).

        In this case is recommended for accuracy that this function
        be called with at least 0.1 seconds between calls.
        """
        blocking = interval is not None and interval > 0.0
        num_cpus = psutil.cpu_count()

        if psutil.POSIX:
            def timer():
                return psutil._timer() * num_cpus
        else:
            def timer():
                return sum(psutil.cpu_times())
        if blocking:
            st1 = timer()
            pt1 = self._proc.cpu_times()
            time.sleep(interval)
            st2 = timer()
            pt2 = self._proc.cpu_times()
        else:
            st1 = self._last_sys_cpu_times
            pt1 = self._last_proc_cpu_times
            st2 = timer()
            pt2 = self._proc.cpu_times()
            if st1 is None or pt1 is None:
                self._last_sys_cpu_times = st2
                self._last_proc_cpu_times = pt2
                return 0.0, 0.0

        delta_user = pt2.user - pt1.user
        delta_system = pt2.system - pt1.system
        delta_time = st2 - st1
        # reset values for next call in case of interval == None
        self._last_sys_cpu_times = st2
        self._last_proc_cpu_times = pt2

        try:
            # The utilization split between all CPUs.
            # Note: a percentage > 100 is legitimate as it can result
            # from a process with multiple threads running on different
            # CPU cores, see:
            # http://stackoverflow.com/questions/1032357
            # https://github.com/giampaolo/psutil/issues/474
            user_percent = ((delta_user / delta_time) * 100) * num_cpus
            system_percent = ((delta_system / delta_time) * 100) * num_cpus
        except ZeroDivisionError:
            # interval was too low
            return 0.0, 0.0
        else:
            return user_percent, system_percent

    def rlimit_nofile(self):
        if hasattr(self, 'rlimit'):
            return self.rlimit(psutil.RLIMIT_NOFILE)[1]

        elif sys.platform.startswith('freebsd'):
            procstat_out, _ = subp.call("procstat -l %s | grep 'openfiles' | awk '{print $5}'" % self.pid, check=False)
            if procstat_out:
                return int(procstat_out[0])

        else:
            # fallback for old systems without rlimit
            cat_limits, _ = subp.call("cat /proc/%s/limits | grep 'Max open files' | awk '{print $5}'" % self.pid, check=False)
            if cat_limits:
                return int(cat_limits[0])
