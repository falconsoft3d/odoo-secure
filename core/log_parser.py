"""
Parses Linux security log files (auth.log / secure) and stores new events
in the SecurityEvent model, using LogReadCursor to avoid re-reading lines.

Log files checked (in order, first found wins):
  /var/log/auth.log      — Debian / Ubuntu
  /var/log/secure        — RHEL / CentOS / Fedora / AlmaLinux
  /var/log/messages      — fallback some distros
"""
import logging
import os
import re
from datetime import datetime

from django.utils import timezone

logger = logging.getLogger('odoo_secure.log_parser')

# Candidate log file paths (checked in order)
CANDIDATE_LOG_FILES = [
    '/var/log/auth.log',
    '/var/log/secure',
    '/var/log/messages',
]

# ── Regex patterns ────────────────────────────────────────────────────────────
# Standard syslog prefix:  May  3 14:22:01 hostname process[pid]:
_SYSLOG_PREFIX = re.compile(
    r'^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+\S+:\s+(.*)'
)

_SSH_FAIL = re.compile(
    r'Failed (?:password|publickey) for (?:invalid user )?(\S+) from ([\d.a-fA-F:]+)'
)
_SSH_SUCCESS = re.compile(
    r'Accepted (?:password|publickey) for (\S+) from ([\d.a-fA-F:]+)'
)
_SSH_INVALID = re.compile(
    r'Invalid user (\S+) from ([\d.a-fA-F:]+)'
)
_SUDO = re.compile(
    r'sudo:\s+(\S+)\s+:.*COMMAND=(.*)'
)


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse syslog timestamp (no year) using current year, UTC-aware."""
    year = timezone.now().year
    try:
        naive = datetime.strptime(f'{year} {ts_str.strip()}', '%Y %b %d %H:%M:%S')
    except ValueError:
        naive = timezone.now().replace(tzinfo=None)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def parse_line(line: str, log_file: str) -> dict | None:
    """
    Parse a single log line. Returns a dict suitable for SecurityEvent.objects.create()
    or None if the line is not a security-relevant event.
    """
    m = _SYSLOG_PREFIX.match(line)
    if not m:
        return None

    ts_str, hostname, body = m.group(1), m.group(2), m.group(3)

    # SSH Failed password / publickey
    r = _SSH_FAIL.search(body)
    if r:
        return dict(
            event_type='ssh_fail',
            timestamp=_parse_timestamp(ts_str),
            username=r.group(1),
            source_ip=r.group(2),
            hostname=hostname,
            raw_line=line.rstrip(),
            log_file=log_file,
        )

    # Invalid user
    r = _SSH_INVALID.search(body)
    if r:
        return dict(
            event_type='ssh_invalid',
            timestamp=_parse_timestamp(ts_str),
            username=r.group(1),
            source_ip=r.group(2),
            hostname=hostname,
            raw_line=line.rstrip(),
            log_file=log_file,
        )

    # SSH Accepted
    r = _SSH_SUCCESS.search(body)
    if r:
        return dict(
            event_type='ssh_success',
            timestamp=_parse_timestamp(ts_str),
            username=r.group(1),
            source_ip=r.group(2),
            hostname=hostname,
            raw_line=line.rstrip(),
            log_file=log_file,
        )

    # sudo usage
    r = _SUDO.search(body)
    if r:
        return dict(
            event_type='sudo',
            timestamp=_parse_timestamp(ts_str),
            username=r.group(1),
            source_ip=None,
            hostname=hostname,
            raw_line=line.rstrip(),
            log_file=log_file,
        )

    return None


def read_security_logs():
    """
    Main task: read new lines from all available security log files,
    parse them and store SecurityEvent records.
    Uses LogReadCursor to remember byte position between runs.
    """
    from core.models import SecurityEvent, LogReadCursor  # late import – Django ready guard

    available = [p for p in CANDIDATE_LOG_FILES if os.path.isfile(p)]
    if not available:
        logger.debug('No se encontraron archivos de log de seguridad en este sistema.')
        return

    new_events = 0
    for log_file in available:
        try:
            cursor, _ = LogReadCursor.objects.get_or_create(
                log_file=log_file,
                defaults={'last_position': 0},
            )

            file_size = os.path.getsize(log_file)

            # Handle log rotation (file got smaller)
            if cursor.last_position > file_size:
                logger.info('Rotación detectada en %s — reiniciando cursor.', log_file)
                cursor.last_position = 0

            if cursor.last_position == file_size:
                continue  # nothing new

            with open(log_file, 'r', errors='replace') as fh:
                fh.seek(cursor.last_position)
                to_create = []
                for line in fh:
                    parsed = parse_line(line, log_file)
                    if parsed:
                        to_create.append(SecurityEvent(**parsed))

                new_pos = fh.tell()

            if to_create:
                SecurityEvent.objects.bulk_create(to_create, ignore_conflicts=True)
                new_events += len(to_create)
                logger.info('Importados %d eventos de %s', len(to_create), log_file)

            cursor.last_position = new_pos
            cursor.save(update_fields=['last_position', 'last_read_at'])

        except PermissionError:
            logger.warning(
                'Sin permiso para leer %s. '
                'Ejecuta Django con el usuario adm o añádelo al grupo adm: '
                'sudo usermod -aG adm www-data',
                log_file,
            )
        except Exception as exc:
            logger.exception('Error leyendo %s: %s', log_file, exc)

    if new_events:
        logger.info('Total eventos de seguridad importados: %d', new_events)
