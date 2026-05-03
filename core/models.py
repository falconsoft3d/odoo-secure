from django.db import models
from django.utils import timezone


class ServerConfig(models.Model):
    STATUS_UNKNOWN = 'unknown'
    STATUS_ONLINE = 'online'
    STATUS_OFFLINE = 'offline'
    STATUS_CHOICES = [
        (STATUS_UNKNOWN, 'Desconocido'),
        (STATUS_ONLINE, 'En línea'),
        (STATUS_OFFLINE, 'Fuera de línea'),
    ]

    name = models.CharField(max_length=150, verbose_name='Nombre del servidor')
    url = models.URLField(verbose_name='URL de comprobación')
    restart_command = models.TextField(
        verbose_name='Comando de reinicio',
        help_text=(
            'Comando shell ejecutado en el sistema host (no dentro de Docker). '
            'Ejemplos: «docker restart odoo» · «docker compose -f /srv/odoo/docker-compose.yml restart» · «sudo systemctl restart odoo»'
        ),
    )
    check_interval = models.PositiveIntegerField(
        default=5,
        verbose_name='Intervalo de chequeo (min)',
        help_text='Cada cuántos minutos se comprobará la URL',
    )
    is_active = models.BooleanField(default=True, verbose_name='Monitoreo activo')
    last_checked_at = models.DateTimeField(null=True, blank=True, verbose_name='Último chequeo')
    last_status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default=STATUS_UNKNOWN, verbose_name='Último estado'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Configuración de servidor'
        verbose_name_plural = 'Configuraciones de servidores'

    def __str__(self):
        return self.name

    @property
    def restart_count(self):
        return self.check_logs.filter(restart_triggered=True).count()

    def is_due(self):
        """Returns True if this server should be checked now."""
        if not self.last_checked_at:
            return True
        elapsed = (timezone.now() - self.last_checked_at).total_seconds() / 60
        return elapsed >= self.check_interval


class ServerCheckLog(models.Model):
    STATUS_ONLINE = 'online'
    STATUS_OFFLINE = 'offline'
    STATUS_ERROR = 'error'
    STATUS_CHOICES = [
        (STATUS_ONLINE, 'En línea'),
        (STATUS_OFFLINE, 'Fuera de línea'),
        (STATUS_ERROR, 'Error'),
    ]

    server = models.ForeignKey(
        ServerConfig, on_delete=models.CASCADE,
        related_name='check_logs', verbose_name='Servidor'
    )
    checked_at = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de chequeo')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, verbose_name='Estado')
    http_code = models.IntegerField(null=True, blank=True, verbose_name='Código HTTP')
    response_time_ms = models.IntegerField(null=True, blank=True, verbose_name='Tiempo de respuesta (ms)')
    restart_triggered = models.BooleanField(default=False, verbose_name='Reinicio disparado')
    restart_success = models.BooleanField(null=True, blank=True, verbose_name='Reinicio exitoso')
    restart_output = models.TextField(blank=True, verbose_name='Salida del comando')
    error_detail = models.TextField(blank=True, verbose_name='Detalle del error')
    is_manual = models.BooleanField(default=False, verbose_name='Reinicio manual')

    class Meta:
        ordering = ['-checked_at']
        verbose_name = 'Log de chequeo'
        verbose_name_plural = 'Logs de chequeos'

    def __str__(self):
        return f'{self.server.name} – {self.checked_at:%Y-%m-%d %H:%M} – {self.status}'


# ── Security log models ─────────────────────────────────────────────────────

class SecurityEvent(models.Model):
    TYPE_SSH_FAIL = 'ssh_fail'
    TYPE_SSH_SUCCESS = 'ssh_success'
    TYPE_SSH_INVALID = 'ssh_invalid'
    TYPE_SUDO = 'sudo'
    TYPE_OTHER = 'other'
    TYPE_CHOICES = [
        (TYPE_SSH_FAIL, 'Login SSH fallido'),
        (TYPE_SSH_SUCCESS, 'Login SSH exitoso'),
        (TYPE_SSH_INVALID, 'Usuario inválido SSH'),
        (TYPE_SUDO, 'Uso de sudo'),
        (TYPE_OTHER, 'Otro'),
    ]

    event_type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name='Tipo')
    timestamp = models.DateTimeField(verbose_name='Fecha del evento', db_index=True)
    username = models.CharField(max_length=150, blank=True, verbose_name='Usuario')
    source_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP origen')
    hostname = models.CharField(max_length=255, blank=True, verbose_name='Hostname')
    raw_line = models.TextField(verbose_name='Línea original')
    log_file = models.CharField(max_length=255, verbose_name='Archivo de log')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Evento de seguridad'
        verbose_name_plural = 'Eventos de seguridad'
        indexes = [
            models.Index(fields=['-timestamp', 'event_type']),
        ]

    def __str__(self):
        return f'{self.event_type} – {self.username} @ {self.source_ip} – {self.timestamp:%Y-%m-%d %H:%M}'

    @property
    def is_threat(self):
        return self.event_type in (self.TYPE_SSH_FAIL, self.TYPE_SSH_INVALID)


class LogReadCursor(models.Model):
    """Tracks the byte offset read so far per log file to avoid re-parsing."""
    log_file = models.CharField(max_length=255, unique=True, verbose_name='Archivo de log')
    last_position = models.BigIntegerField(default=0, verbose_name='Última posición (bytes)')
    last_read_at = models.DateTimeField(auto_now=True, verbose_name='Última lectura')

    class Meta:
        verbose_name = 'Cursor de log'
        verbose_name_plural = 'Cursores de log'

    def __str__(self):
        return f'{self.log_file} @ {self.last_position}'


# ── Odoo application log models ─────────────────────────────────────────────

class OdooLogSource(models.Model):
    """Configurable path to the Odoo server log file."""
    name = models.CharField(max_length=150, verbose_name='Nombre', default='Odoo Server')
    log_path = models.CharField(
        max_length=500,
        default='/var/log/odoo/odoo-server.log',
        verbose_name='Ruta del archivo de log',
        help_text='Ruta absoluta en el sistema host, ej. /var/log/odoo/odoo-server.log',
    )
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Fuente de log Odoo'
        verbose_name_plural = 'Fuentes de log Odoo'

    def __str__(self):
        return f'{self.name} ({self.log_path})'


class OdooLogEntry(models.Model):
    LEVEL_ERROR = 'ERROR'
    LEVEL_WARNING = 'WARNING'
    LEVEL_INFO = 'INFO'
    LEVEL_DEBUG = 'DEBUG'
    LEVEL_CRITICAL = 'CRITICAL'
    LEVEL_CHOICES = [
        (LEVEL_ERROR, 'Error'),
        (LEVEL_WARNING, 'Warning'),
        (LEVEL_CRITICAL, 'Critical'),
        (LEVEL_INFO, 'Info'),
        (LEVEL_DEBUG, 'Debug'),
    ]

    source = models.ForeignKey(
        OdooLogSource, on_delete=models.CASCADE,
        related_name='log_entries', verbose_name='Fuente'
    )
    timestamp = models.DateTimeField(verbose_name='Fecha del evento', db_index=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, verbose_name='Nivel', db_index=True)
    pid = models.IntegerField(null=True, blank=True, verbose_name='PID')
    database = models.CharField(max_length=150, blank=True, verbose_name='Base de datos')
    logger = models.CharField(max_length=255, blank=True, verbose_name='Logger', db_index=True)
    message = models.TextField(verbose_name='Mensaje')
    raw_line = models.TextField(verbose_name='Línea original')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Entrada de log Odoo'
        verbose_name_plural = 'Entradas de log Odoo'
        indexes = [
            models.Index(fields=['-timestamp', 'level']),
        ]

    def __str__(self):
        return f'[{self.level}] {self.logger}: {self.message[:80]}'

