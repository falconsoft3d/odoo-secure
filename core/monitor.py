"""
Monitor task: checks each active ServerConfig URL.
If the server is offline, executes the restart command and logs the result.
"""
import logging
import subprocess
import time

import urllib.request
import urllib.error

from django.utils import timezone

logger = logging.getLogger('odoo_secure.monitor')


def check_url(url: str, timeout: int = 10) -> tuple[str, int | None, int | None]:
    """
    Returns (status, http_code, response_time_ms).
    status is 'online', 'offline', or 'error'.
    """
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'OdooSecure-Monitor/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = int((time.monotonic() - start) * 1000)
            code = resp.status
            if 200 <= code < 400:
                return 'online', code, elapsed
            return 'offline', code, elapsed
    except urllib.error.HTTPError as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return 'offline', exc.code, elapsed
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        logger.warning('Error checking %s: %s', url, exc)
        return 'error', None, elapsed


def run_restart_command(command: str) -> tuple[bool, str]:
    """Runs the restart command. Returns (success, output)."""
    try:
        result = subprocess.run(
            command,
            shell=True,          # noqa: S602 – intentional: admin-configured command
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, 'El comando superó el tiempo límite de 60 s'
    except Exception as exc:
        return False, str(exc)


def check_all_servers():
    """
    Main task: iterates all active servers that are due for a check.
    Called every minute by the scheduler.
    """
    # Import inside function to ensure Django apps are ready
    from core.models import ServerConfig, ServerCheckLog  # noqa: PLC0415

    servers = ServerConfig.objects.filter(is_active=True)
    if not servers.exists():
        return

    for server in servers:
        if not server.is_due():
            continue

        logger.info('Checking %s → %s', server.name, server.url)
        status, http_code, response_ms = check_url(server.url)

        restart_triggered = False
        restart_success = None
        restart_output = ''
        error_detail = ''

        if status in ('offline', 'error'):
            logger.warning('%s is %s (HTTP %s). Running restart command…', server.name, status, http_code)
            restart_triggered = True
            restart_success, restart_output = run_restart_command(server.restart_command)
            log_level = logging.INFO if restart_success else logging.ERROR
            logger.log(log_level, 'Restart for %s: success=%s output=%r', server.name, restart_success, restart_output[:200])
        else:
            error_detail = ''

        # Persist command log when a restart was triggered
        if restart_triggered:
            from core.models import CommandLog  # noqa: PLC0415
            CommandLog.objects.create(
                command=server.restart_command,
                server=server,
                triggered_by=None,
                source=CommandLog.SOURCE_AUTO,
                success=bool(restart_success),
                output=restart_output,
            )

        # Persist log
        ServerCheckLog.objects.create(
            server=server,
            status=status,
            http_code=http_code,
            response_time_ms=response_ms,
            restart_triggered=restart_triggered,
            restart_success=restart_success,
            restart_output=restart_output,
            error_detail=error_detail,
        )

        # Update server status
        server.last_checked_at = timezone.now()
        server.last_status = status if status in ('online', 'offline') else 'offline'
        server.save(update_fields=['last_checked_at', 'last_status'])
