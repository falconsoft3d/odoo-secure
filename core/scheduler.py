import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger('odoo_secure.scheduler')

_scheduler = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone='UTC')
    return _scheduler


def start():
    scheduler = get_scheduler()
    if scheduler.running:
        return

    from core.monitor import check_all_servers
    from core.log_parser import read_security_logs
    from core.odoo_log_parser import read_odoo_logs

    scheduler.add_job(
        check_all_servers,
        trigger=IntervalTrigger(minutes=1),
        id='check_all_servers',
        name='Chequeo de servidores Odoo',
        replace_existing=True,
        misfire_grace_time=30,
    )
    scheduler.add_job(
        read_security_logs,
        trigger=IntervalTrigger(minutes=1),
        id='read_security_logs',
        name='Lectura de logs de seguridad',
        replace_existing=True,
        misfire_grace_time=30,
    )
    scheduler.add_job(
        read_odoo_logs,
        trigger=IntervalTrigger(minutes=1),
        id='read_odoo_logs',
        name='Lectura de logs de aplicación Odoo',
        replace_existing=True,
        misfire_grace_time=30,
    )
    scheduler.start()
    logger.info('Scheduler iniciado — chequeo, logs de seguridad y logs Odoo cada 1 minuto.')


def shutdown():
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info('Scheduler detenido.')
