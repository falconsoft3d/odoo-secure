import logging
import sys

from django.apps import AppConfig

logger = logging.getLogger('odoo_secure.scheduler')


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        # Only start the scheduler in the main process (not in migrations, tests, or reloader children)
        if 'migrate' in sys.argv or 'makemigrations' in sys.argv or 'test' in sys.argv:
            return
        # In development, Django's autoreloader sets RUN_MAIN='false' in the parent process
        # to avoid double-starting. In production (gunicorn), RUN_MAIN is not set at all.
        import os
        if os.environ.get('RUN_MAIN') != 'false':
            from core.scheduler import start
            start()

