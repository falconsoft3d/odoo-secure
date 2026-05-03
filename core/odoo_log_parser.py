"""
odoo_log_parser.py — reads Odoo server log files and stores ERROR/WARNING entries.

Odoo log format (one line per entry, multi-line tracebacks end at next timestamp):
  2024-01-15 10:30:00,123 1234 ERROR mydb odoo.http: message here
  2024-01-15 10:30:01,456 1234 WARNING mydb odoo.models.write: another message

Only ERROR, WARNING, and CRITICAL levels are persisted to avoid flooding the DB.
Uses LogReadCursor (keyed by log_path) to track byte offset and handle log rotation.
"""
import logging
import os
import re
from datetime import datetime

logger = logging.getLogger('odoo_secure.odoo_log_parser')

# Odoo log line regex:
#   2024-01-15 10:30:00,123 1234 ERROR mydb odoo.module.name: message
_LINE_RE = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)'  # timestamp
    r'\s+(\d+)'                                        # pid
    r'\s+(ERROR|WARNING|CRITICAL|INFO|DEBUG)'          # level
    r'\s+(\S+)'                                        # database
    r'\s+([\w.]+):'                                    # logger
    r'\s*(.*)',                                         # message
    re.DOTALL,
)

CAPTURE_LEVELS = {'ERROR', 'WARNING', 'CRITICAL'}


def _parse_timestamp(ts_str: str) -> datetime | None:
    """Parse Odoo timestamp '2024-01-15 10:30:00,123' → naive datetime."""
    try:
        return datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S,%f')
    except ValueError:
        return None


def read_odoo_logs():
    """
    Main job: iterate all active OdooLogSource entries, read new lines
    from each log file, parse and bulk-insert ERROR/WARNING/CRITICAL entries.
    """
    # Import inside function so Django apps are ready when called from scheduler
    from django.utils import timezone
    from .models import OdooLogSource, OdooLogEntry, LogReadCursor

    sources = OdooLogSource.objects.filter(is_active=True)
    if not sources.exists():
        return

    for source in sources:
        log_path = source.log_path
        if not os.path.isfile(log_path):
            logger.debug('Odoo log not found: %s', log_path)
            continue

        cursor, _ = LogReadCursor.objects.get_or_create(
            log_file=f'odoo:{log_path}',
            defaults={'last_position': 0},
        )

        try:
            file_size = os.path.getsize(log_path)
        except OSError:
            continue

        # Detect log rotation: file is smaller than saved cursor
        if file_size < cursor.last_position:
            logger.info('Odoo log rotated, resetting cursor: %s', log_path)
            cursor.last_position = 0
            cursor.save(update_fields=['last_position'])

        if file_size == cursor.last_position:
            continue  # nothing new

        try:
            fh = open(log_path, 'r', encoding='utf-8', errors='replace')
        except PermissionError:
            logger.warning(
                'No se puede leer %s. '
                'Asegúrate de que el usuario tiene permiso: '
                'sudo chmod o+r %s  o  sudo usermod -aG adm <user>',
                log_path, log_path,
            )
            continue

        with fh:
            fh.seek(cursor.last_position)
            new_position = cursor.last_position

            # We accumulate a "current" entry to support multi-line tracebacks
            current: dict | None = None
            entries_to_create = []

            def flush_current():
                nonlocal current
                if current and current['level'] in CAPTURE_LEVELS:
                    entries_to_create.append(
                        OdooLogEntry(
                            source=source,
                            timestamp=current['timestamp'],
                            level=current['level'],
                            pid=current['pid'],
                            database=current['database'],
                            logger=current['logger'],
                            message=current['message'].strip(),
                            raw_line=current['raw_line'].strip(),
                        )
                    )
                current = None

            for line in fh:
                new_position += len(line.encode('utf-8', errors='replace'))
                m = _LINE_RE.match(line)
                if m:
                    flush_current()
                    ts = _parse_timestamp(m.group(1))
                    if ts is None:
                        continue
                    # Make timezone-aware
                    from django.utils.timezone import make_aware, is_naive
                    if is_naive(ts):
                        ts = make_aware(ts)
                    current = {
                        'timestamp': ts,
                        'pid': int(m.group(2)),
                        'level': m.group(3),
                        'database': m.group(4),
                        'logger': m.group(5),
                        'message': m.group(6),
                        'raw_line': line,
                    }
                elif current:
                    # Continuation line (traceback, etc.) – append to current message
                    current['message'] += '\n' + line.rstrip()
                    current['raw_line'] += line

            flush_current()

        if entries_to_create:
            OdooLogEntry.objects.bulk_create(entries_to_create, ignore_conflicts=True)
            logger.info(
                'Odoo log [%s]: +%d entradas (%d ERROR/WARNING/CRITICAL)',
                log_path,
                len(entries_to_create),
                len(entries_to_create),
            )

        cursor.last_position = new_position
        cursor.save(update_fields=['last_position'])
