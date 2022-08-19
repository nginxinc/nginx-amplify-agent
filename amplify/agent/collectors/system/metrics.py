# -*- coding: utf-8 -*-
import os
import re
import time
from collections import defaultdict

import psutil

from amplify.agent.common.context import context
from amplify.agent.common.util import host
from amplify.agent.common.util import subp
from amplify.agent.collectors.abstract import AbstractMetricsCollector

__author__ = "Mike Belov"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "Mike Belov"
__email__ = "dedm@nginx.com"


class SystemMetricsCollector(AbstractMetricsCollector):
    """
    Unix system metrics collector
    """
    short_name = 'sys_metrics'
    status_metric_key = 'controller.agent.status'

    def __init__(self, **kwargs):
        super(SystemMetricsCollector, self).__init__(**kwargs)
        self.register(
            self.agent_cpu,
            self.agent_memory_info,
            self.container,
            self.virtual_memory,
            self.swap,
            self.cpu,
            self.disk_partitions,
            self.disk_io_counters,
            self.net_io_counters,
            self.la,
            self.netstat
        )

    def container(self):
        """ send counter for container object """
        if self.object.type == 'container':
            self.object.statsd.latest('controller.agent.container.count', 1)

    def agent_cpu(self):
        """ agent cpu times """
        user, system = context.psutil_process.cpu_percent()
        self.object.statsd.gauge('controller.agent.cpu.user', user)
        self.object.statsd.gauge('controller.agent.cpu.system', system)

    def agent_memory_info(self):
        """
        agent memory info

        controller.agent.mem.rss
        controller.agent.mem.vms
        """
        mem_info = context.psutil_process.memory_info()
        self.object.statsd.gauge('controller.agent.mem.rss', mem_info.rss)
        self.object.statsd.gauge('controller.agent.mem.vms', mem_info.vms)

    def virtual_memory(self):
        """ virtual memory """
        virtual_memory = psutil.virtual_memory()
        self.object.statsd.gauge('system.mem.total', virtual_memory.total)
        self.object.statsd.gauge('system.mem.used', (virtual_memory.total - virtual_memory.available))
        self.object.statsd.gauge('system.mem.used.all', virtual_memory.used)
        self.object.statsd.gauge('system.mem.cached', virtual_memory.cached)
        self.object.statsd.gauge('system.mem.buffered', virtual_memory.buffers)
        self.object.statsd.gauge('system.mem.free', virtual_memory.free)
        self.object.statsd.gauge('system.mem.pct_used', virtual_memory.percent)
        self.object.statsd.gauge('system.mem.available', virtual_memory.available)

        # BSD
        if hasattr(virtual_memory, 'shared'):
            self.object.statsd.gauge('system.mem.shared', virtual_memory.shared)

    def swap(self):
        """ swap """
        swap_memory = psutil.swap_memory()
        self.object.statsd.gauge('system.swap.total', swap_memory.total)
        self.object.statsd.gauge('system.swap.used', swap_memory.used)
        self.object.statsd.gauge('system.swap.free', swap_memory.free)
        self.object.statsd.gauge('system.swap.pct_free', swap_memory.percent)

    def cpu(self):
        """ cpu """
        cpu_times = psutil.cpu_times_percent()
        self.object.statsd.gauge('system.cpu.user', (cpu_times.user + cpu_times.nice))
        
        if hasattr(cpu_times, 'softirq'):
            self.object.statsd.gauge('system.cpu.system', (cpu_times.system + cpu_times.irq + cpu_times.softirq))
        else:
            self.object.statsd.gauge('system.cpu.system', (cpu_times.system + cpu_times.irq))

        self.object.statsd.gauge('system.cpu.idle', cpu_times.idle)

        if hasattr(cpu_times, 'iowait'):
            self.object.statsd.gauge('system.cpu.iowait', cpu_times.iowait)

        if hasattr(cpu_times, 'steal'):
            self.object.statsd.gauge('system.cpu.stolen', cpu_times.steal)

    def disk_partitions(self):
        """ disk partitions usage """
        overall_used, overall_total, overall_free = 0, 0, 0
        for part in psutil.disk_partitions(all=False):
            if 'cdrom' in part.opts or part.fstype == '':
                continue
            usage = psutil.disk_usage(part.mountpoint)
            overall_used += usage.used
            overall_total += usage.total
            overall_free += usage.free
            self.object.statsd.gauge('system.disk.total|%s' % part.mountpoint, usage.total)
            self.object.statsd.gauge('system.disk.used|%s' % part.mountpoint, usage.used)
            self.object.statsd.gauge('system.disk.free|%s' % part.mountpoint, usage.free)

            in_use = float(usage.used) / float(usage.total) * 100.0 if usage.total else 0.0
            self.object.statsd.gauge('system.disk.in_use|%s' % part.mountpoint, in_use)

        self.object.statsd.gauge('system.disk.total', overall_total)
        self.object.statsd.gauge('system.disk.used', overall_used)
        self.object.statsd.gauge('system.disk.free', overall_free)

        in_use_total = float(overall_used) / float(overall_total) * 100.0 if overall_total else 0.0
        self.object.statsd.gauge('system.disk.in_use', in_use_total)

    def disk_io_counters(self):
        """ disk io counters """

        real_block_devs = host.block_devices()
        disk_counters = {'__all__': psutil.disk_io_counters(perdisk=False)}
        disk_counters.update(psutil.disk_io_counters(perdisk=True))

        simple_metrics = {
            'write_count': ['system.io.iops_w', 1, self.object.statsd.incr],
            'write_bytes': ['system.io.kbs_w', 1024, self.object.statsd.incr],
            'read_count': ['system.io.iops_r', 1, self.object.statsd.incr],
            'read_bytes': ['system.io.kbs_r', 1024, self.object.statsd.incr],
        }

        complex_metrics = {
            'write_time': ['system.io.wait_w', 1, self.object.statsd.gauge],
            'read_time': ['system.io.wait_r', 1, self.object.statsd.gauge],
        }

        for disk, io in disk_counters.items():
            # do not process virtual devices
            disk_is_physical = False
            for real_dev_name in real_block_devs:
                if disk.startswith(real_dev_name):
                    disk_is_physical = True

            # check to see if it is __all__ special name
            if disk == '__all__':
                disk_is_physical = True

            if not disk_is_physical:
                continue

            for method, description in simple_metrics.items():
                new_stamp, new_value = time.time(), getattr(io, method)
                prev_stamp, prev_value = self.previous_counters.get(disk, {}).get(method, (None, None))

                if prev_stamp and new_value >= prev_value:
                    metric_name, value_divider, stat_func = description
                    delta_value = (new_value - prev_value) / value_divider
                    metric_full_name = metric_name if disk == '__all__' else '%s|%s' % (metric_name, disk)
                    stat_func(metric_full_name, delta_value)

                    if method == 'write_count':
                        complex_metrics['write_time'][1] = delta_value
                    elif method == 'read_count':
                        complex_metrics['read_time'][1] = delta_value

                self.previous_counters[disk][method] = (new_stamp, new_value)

            for method, description in complex_metrics.items():
                new_stamp, new_value = time.time(), getattr(io, method)
                prev_stamp, prev_value = self.previous_counters.get(disk, {}).get(method, (None, None))

                if isinstance(prev_value, (int, float, complex)) and prev_stamp != new_stamp:
                    metric_name, value_divider, stat_func = description
                    if value_divider:
                        delta_value = (new_value - prev_value) / float(value_divider)
                    else:
                        delta_value = 0
                    metric_full_name = metric_name if disk == '__all__' else '%s|%s' % (metric_name, disk)
                    stat_func(metric_full_name, delta_value)

                self.previous_counters[disk][method] = (new_stamp, new_value)

    def net_io_counters(self):
        """
        net io counters

        total counters do not include lo interface
        """
        totals = defaultdict(int)
        metrics = {
            'packets_sent': 'system.net.packets_out.count',
            'packets_recv': 'system.net.packets_in.count',
            'bytes_sent': 'system.net.bytes_sent',
            'bytes_recv': 'system.net.bytes_rcvd',
            'errin': 'system.net.packets_in.error',
            'errout': 'system.net.packets_out.error',
            'dropin': 'system.net.drops_in.count',
            'dropout': 'system.net.drops_out.count'
        }

        net_io_counters = psutil.net_io_counters(pernic=True)
        for interface in host.alive_interfaces():
            io = net_io_counters.get(interface)

            if not io:
                continue

            for method, metric in metrics.items():
                new_stamp, new_value = time.time(), getattr(io, method)
                prev_stamp, prev_value = self.previous_counters.get(interface, {}).get(metric, (None, None))

                if prev_stamp and new_value >= prev_value:
                    delta_value = new_value - prev_value
                    metric_full_name = '%s|%s' % (metric, interface)
                    self.object.statsd.incr(metric_full_name, delta_value)

                    # collect total values
                    if not interface.startswith('lo'):
                        totals[metric] += delta_value

                self.previous_counters[interface][metric] = (new_stamp, new_value)

        # send total values
        for metric, value in totals.items():
            self.object.statsd.incr(metric, value)

    def la(self):
        """ load average """
        la = os.getloadavg()
        self.object.statsd.gauge('system.load.1', la[0])
        self.object.statsd.gauge('system.load.5', la[1])
        self.object.statsd.gauge('system.load.15', la[2])

    def netstat(self):
        """
        netstat -s

        (check for "SYNs to LISTEN sockets dropped” and "times the listen queue of a socket overflowed")
        """
        new_stamp = time.time()
        netstat_out, _ = subp.call("netstat -s | grep -i 'times the listen queue of a socket overflowed'", check=False)
        gwe = re.match('\s*(\d+)\s*', netstat_out.pop(0))

        new_value = int(gwe.group(1)) if gwe else 0
        prev_stamp, prev_value = self.previous_counters.get('system.net.listen_overflows', (None, None))
        if prev_stamp:
            delta_value = new_value - prev_value
            self.object.statsd.incr('system.net.listen_overflows', delta_value)

        self.previous_counters['system.net.listen_overflows'] = (new_stamp, new_value)


class GenericLinuxSystemMetricsCollector(SystemMetricsCollector):
    pass


class GentooSystemMetricsCollector(SystemMetricsCollector):
    pass


class DebianSystemMetricsCollector(SystemMetricsCollector):
    pass


class CentosSystemMetricsCollector(SystemMetricsCollector):
    pass


class FreebsdSystemMetricsCollector(SystemMetricsCollector):
    pass

