import logging
import time
import traceback

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger('odoo_secure.scheduler')

_scheduler = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone='UTC')
    return _scheduler


def _tracked(job_id, fn):
    """Wrapper: runs fn(), records duration and result in SchedulerLog."""
    def wrapper():
        from django.utils import timezone
        from core.models import SchedulerLog  # noqa: PLC0415

        started = timezone.now()
        t0 = time.monotonic()
        status = SchedulerLog.STATUS_OK
        detail = ''
        try:
            fn()
        except Exception:
            status = SchedulerLog.STATUS_ERROR
            detail = traceback.format_exc()
            logger.exception('Error en job %s', job_id)
        finally:
            duration_ms = int((time.monotonic() - t0) * 1000)
            finished = timezone.now()
            try:
                SchedulerLog.objects.create(
                    job_id=job_id,
                    started_at=started,
                    finished_at=finished,
                    duration_ms=duration_ms,
                    status=status,
                    detail=detail,
                )
            except Exception:
                logger.exception('No se pudo guardar SchedulerLog para %s', job_id)

    wrapper.__name__ = job_id
    return wrapper


def start():
    scheduler = get_scheduler()
    if scheduler.running:
        return

    from core.log_parser import read_security_logs
    from core.odoo_log_parser import read_odoo_logs
    from core.system_stats import record_metrics

    scheduler.add_job(
        _tracked('record_system_metrics', record_metrics),
        trigger=IntervalTrigger(minutes=1),
        id='record_system_metrics',
        name='Registro de métricas CPU/RAM',
        replace_existing=True,
        misfire_grace_time=30,
    )
    scheduler.add_job(
        _tracked('read_security_logs', read_security_logs),
        trigger=IntervalTrigger(minutes=1),
        id='read_security_logs',
        name='Lectura de logs de seguridad',
        replace_existing=True,
        misfire_grace_time=30,
    )
    scheduler.add_job(
        _tracked('read_odoo_logs', read_odoo_logs),
        trigger=IntervalTrigger(minutes=1),
        id='read_odoo_logs',
        name='Lectura de logs de aplicación Odoo',
        replace_existing=True,
        misfire_grace_time=30,
    )
    scheduler.start()
    logger.info('Scheduler iniciado — métricas, logs de seguridad y logs Odoo cada 1 minuto.')


def shutdown():
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info('Scheduler detenido.')
