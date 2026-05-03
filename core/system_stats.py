"""
system_stats.py — reads host-level performance metrics using psutil.
All data is from the machine running Django, NOT from inside any Docker container.
"""
import os
import platform
import time
from datetime import datetime, timedelta

import psutil


def _bytes_to(value, unit='GB'):
    divisors = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
    return round(value / divisors[unit], 2)


def get_cpu():
    percent_per_core = psutil.cpu_percent(interval=0.5, percpu=True)
    freq = psutil.cpu_freq()
    return {
        'percent': round(sum(percent_per_core) / len(percent_per_core), 1),
        'per_core': [round(p, 1) for p in percent_per_core],
        'cores_logical': psutil.cpu_count(logical=True),
        'cores_physical': psutil.cpu_count(logical=False),
        'freq_current': round(freq.current, 0) if freq else None,
        'freq_max': round(freq.max, 0) if freq and freq.max else None,
    }


def get_memory():
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return {
        'total_gb': _bytes_to(vm.total),
        'used_gb': _bytes_to(vm.used),
        'available_gb': _bytes_to(vm.available),
        'percent': vm.percent,
        'swap_total_gb': _bytes_to(sw.total),
        'swap_used_gb': _bytes_to(sw.used),
        'swap_percent': sw.percent,
    }


def get_disks():
    disks = []
    for part in psutil.disk_partitions(all=False):
        # Skip pseudo filesystems
        if part.fstype in ('', 'squashfs', 'tmpfs', 'devtmpfs', 'overlay'):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except PermissionError:
            continue
        disks.append({
            'device': part.device,
            'mountpoint': part.mountpoint,
            'fstype': part.fstype,
            'total_gb': _bytes_to(usage.total),
            'used_gb': _bytes_to(usage.used),
            'free_gb': _bytes_to(usage.free),
            'percent': usage.percent,
        })
    return disks


def get_network():
    counters = psutil.net_io_counters(pernic=True)
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    ifaces = []
    for name, counter in counters.items():
        st = stats.get(name)
        if st and not st.isup:
            continue
        # Skip loopback and virtual/tunnel interfaces unless they have real traffic
        if name in ('lo', 'lo0'):
            continue
        if any(name.startswith(p) for p in ('utun', 'ipsec', 'llw', 'awdl', 'anpi', 'bridge', 'veth', 'br-')):
            continue
        addr_list = addrs.get(name, [])
        ipv4 = next(
            (a.address for a in addr_list if a.family.name == 'AF_INET'), '–'
        )
        ifaces.append({
            'name': name,
            'ipv4': ipv4,
            'sent_mb': _bytes_to(counter.bytes_sent, 'MB'),
            'recv_mb': _bytes_to(counter.bytes_recv, 'MB'),
            'packets_sent': counter.packets_sent,
            'packets_recv': counter.packets_recv,
            'errin': counter.errin,
            'errout': counter.errout,
            'speed_mbps': st.speed if st else None,
        })
    return ifaces


def get_load():
    try:
        load1, load5, load15 = os.getloadavg()
    except (AttributeError, OSError):
        load1 = load5 = load15 = None
    return {'load1': round(load1, 2) if load1 is not None else None,
            'load5': round(load5, 2) if load5 is not None else None,
            'load15': round(load15, 2) if load15 is not None else None}


def get_uptime():
    boot_ts = psutil.boot_time()
    boot_dt = datetime.fromtimestamp(boot_ts)
    delta = timedelta(seconds=int(time.time() - boot_ts))
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, _ = divmod(rem, 60)
    return {
        'boot_time': boot_dt.strftime('%d/%m/%Y %H:%M'),
        'uptime_str': f'{days}d {hours}h {minutes}m',
        'days': days,
        'hours': hours,
        'minutes': minutes,
    }


def get_top_processes(n=10):
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent', 'status']):
        try:
            info = p.info
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # Sort by CPU then memory
    procs.sort(key=lambda x: (x.get('cpu_percent') or 0), reverse=True)
    return procs[:n]


def get_system_info():
    uname = platform.uname()
    return {
        'hostname': uname.node,
        'os': f'{uname.system} {uname.release}',
        'arch': uname.machine,
        'python': platform.python_version(),
    }


def collect_all():
    """Returns a single dict with all metrics."""
    return {
        'cpu': get_cpu(),
        'memory': get_memory(),
        'disks': get_disks(),
        'network': get_network(),
        'load': get_load(),
        'uptime': get_uptime(),
        'processes': get_top_processes(),
        'system': get_system_info(),
    }


def record_metrics():
    """Records a CPU/RAM snapshot to the database (called by the scheduler)."""
    import psutil
    from django.utils import timezone
    from core.models import SystemMetric

    cpu = psutil.cpu_percent(interval=0.3)
    ram = psutil.virtual_memory().percent
    SystemMetric.objects.create(
        recorded_at=timezone.now(),
        cpu_percent=cpu,
        ram_percent=ram,
    )
    # Keep only last 7 days to avoid unbounded growth
    cutoff = timezone.now() - __import__('datetime').timedelta(days=7)
    SystemMetric.objects.filter(recorded_at__lt=cutoff).delete()
