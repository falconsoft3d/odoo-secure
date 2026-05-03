from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.views import LoginView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView, View
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.urls import reverse_lazy
from django.http import HttpResponseNotAllowed
from .models import ServerConfig, ServerCheckLog, SecurityEvent, OdooLogSource, OdooLogEntry, CommandLog
from .forms import ServerConfigForm, OdooLogSourceForm


def redirect_root(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')


class CustomLoginView(LoginView):
    template_name = 'core/login.html'
    form_class = AuthenticationForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Odoo Secure – Iniciar sesión'
        return context


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'core/dashboard.html'
    login_url = '/login/'

    def get_context_data(self, **kwargs):
        from django.utils.timezone import now

        context = super().get_context_data(**kwargs)
        today = now().date()
        active_servers = ServerConfig.objects.filter(is_active=True)
        offline_count = active_servers.filter(last_status='offline').count()
        checks_today = ServerCheckLog.objects.filter(checked_at__date=today).count()
        restarts_today = ServerCheckLog.objects.filter(
            checked_at__date=today, restart_triggered=True
        ).count()
        threats_today = SecurityEvent.objects.filter(
            timestamp__date=today,
            event_type__in=['ssh_fail', 'ssh_invalid'],
        ).count()

        context['title'] = 'Dashboard de Seguridad'
        context['stats'] = [
            {'label': 'Servidores monitoreados', 'value': active_servers.count(), 'icon': 'server', 'color': 'blue'},
            {'label': 'Fuera de línea ahora', 'value': offline_count, 'icon': 'alert', 'color': 'red'},
            {'label': 'Reinicios hoy', 'value': restarts_today, 'icon': 'shield', 'color': 'purple'},
            {'label': 'Amenazas hoy', 'value': threats_today, 'icon': 'lock', 'color': 'orange'},
        ]
        context['recent_logs'] = ServerCheckLog.objects.select_related('server').order_by('-checked_at')[:10]
        context['recent_security'] = SecurityEvent.objects.order_by('-timestamp')[:10]
        return context


# ── Server Config CRUD ──────────────────────────────────────────────────────

class ServerConfigListView(LoginRequiredMixin, ListView):
    model = ServerConfig
    template_name = 'core/config/list.html'
    context_object_name = 'servers'
    login_url = '/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Servidores'
        return context


class ServerConfigCreateView(LoginRequiredMixin, CreateView):
    model = ServerConfig
    form_class = ServerConfigForm
    template_name = 'core/config/form.html'
    success_url = reverse_lazy('servers')
    login_url = '/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Agregar servidor'
        context['action'] = 'Guardar servidor'
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Servidor agregado correctamente.')
        return super().form_valid(form)


class ServerConfigUpdateView(LoginRequiredMixin, UpdateView):
    model = ServerConfig
    form_class = ServerConfigForm
    template_name = 'core/config/form.html'
    success_url = reverse_lazy('servers')
    login_url = '/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Editar – {self.object.name}'
        context['action'] = 'Guardar cambios'
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Configuración actualizada.')
        return super().form_valid(form)


class ServerConfigDeleteView(LoginRequiredMixin, DeleteView):
    model = ServerConfig
    template_name = 'core/config/confirm_delete.html'
    success_url = reverse_lazy('servers')
    login_url = '/login/'

    def form_valid(self, form):
        messages.success(self.request, f'Servidor «{self.object.name}» eliminado.')
        return super().form_valid(form)


class ServerHistoryView(LoginRequiredMixin, DetailView):
    model = ServerConfig
    template_name = 'core/config/history.html'
    context_object_name = 'server'
    login_url = '/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Historial – {self.object.name}'
        context['logs'] = self.object.check_logs.order_by('-checked_at')[:100]
        context['restart_count'] = self.object.restart_count
        context['total_checks'] = self.object.check_logs.count()
        return context


class ServerManualRestartView(LoginRequiredMixin, View):
    """Ejecuta el comando de reinicio manualmente y registra el log como is_manual=True."""
    login_url = '/login/'

    def post(self, request, pk):
        server = get_object_or_404(ServerConfig, pk=pk)
        from .monitor import run_restart_command, check_url

        # Ejecutar el comando de reinicio
        success, output = run_restart_command(server.restart_command)

        # Intentar verificar el estado luego del reinicio
        status, http_code, response_time_ms = check_url(server.url)

        ServerCheckLog.objects.create(
            server=server,
            status=status,
            http_code=http_code,
            response_time_ms=response_time_ms,
            restart_triggered=True,
            restart_success=success,
            restart_output=output,
            is_manual=True,
        )

        CommandLog.objects.create(
            command=server.restart_command,
            server=server,
            triggered_by=request.user,
            source=CommandLog.SOURCE_MANUAL,
            success=success,
            output=output,
        )

        # Actualizar último estado del servidor
        server.last_status = status
        from django.utils import timezone
        server.last_checked_at = timezone.now()
        server.save(update_fields=['last_status', 'last_checked_at'])

        if success:
            messages.success(request, f'✓ Servidor «{server.name}» reiniciado correctamente.')
        else:
            messages.error(request, f'✗ El reinicio de «{server.name}» falló. Revisa el historial.')

        return redirect('servers')

    def get(self, request, pk):
        return HttpResponseNotAllowed(['POST'])


class SecurityLogView(LoginRequiredMixin, ListView):
    model = SecurityEvent
    template_name = 'core/security/list.html'
    context_object_name = 'events'
    paginate_by = 50
    login_url = '/login/'

    def get_queryset(self):
        qs = SecurityEvent.objects.all()
        event_type = self.request.GET.get('type')
        ip_filter = self.request.GET.get('ip', '').strip()
        user_filter = self.request.GET.get('user', '').strip()
        if event_type:
            qs = qs.filter(event_type=event_type)
        if ip_filter:
            qs = qs.filter(source_ip__icontains=ip_filter)
        if user_filter:
            qs = qs.filter(username__icontains=user_filter)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Accesos y seguridad'
        context['total'] = SecurityEvent.objects.count()
        context['threats'] = SecurityEvent.objects.filter(
            event_type__in=['ssh_fail', 'ssh_invalid']
        ).count()
        context['successes'] = SecurityEvent.objects.filter(
            event_type='ssh_success'
        ).count()
        context['type_filter'] = self.request.GET.get('type', '')
        context['ip_filter'] = self.request.GET.get('ip', '')
        context['user_filter'] = self.request.GET.get('user', '')
        context['event_type_choices'] = SecurityEvent.TYPE_CHOICES
        return context


class SystemStatsView(LoginRequiredMixin, TemplateView):
    template_name = 'core/system/stats.html'
    login_url = '/login/'

    def get_context_data(self, **kwargs):
        from .system_stats import collect_all
        context = super().get_context_data(**kwargs)
        context['title'] = 'Rendimiento del sistema'
        context['active_nav'] = 'system'
        context['stats'] = collect_all()
        return context


# ── Odoo Log views ────────────────────────────────────────────────────────

class OdooLogListView(LoginRequiredMixin, ListView):
    model = OdooLogEntry
    template_name = 'core/odoo_logs/list.html'
    context_object_name = 'logs'
    paginate_by = 50
    login_url = '/login/'

    def get_queryset(self):
        qs = OdooLogEntry.objects.select_related('source').all()
        level = self.request.GET.get('level', '')
        source_id = self.request.GET.get('source', '')
        search = self.request.GET.get('q', '').strip()
        if level:
            qs = qs.filter(level=level)
        if source_id:
            qs = qs.filter(source_id=source_id)
        if search:
            qs = qs.filter(message__icontains=search) | qs.filter(logger__icontains=search)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'odoo_logs'
        context['level_filter'] = self.request.GET.get('level', '')
        context['source_filter'] = self.request.GET.get('source', '')
        context['search_filter'] = self.request.GET.get('q', '')
        context['level_choices'] = OdooLogEntry.LEVEL_CHOICES
        context['sources'] = OdooLogSource.objects.all()
        context['total'] = OdooLogEntry.objects.count()
        context['error_count'] = OdooLogEntry.objects.filter(level='ERROR').count()
        context['warning_count'] = OdooLogEntry.objects.filter(level='WARNING').count()
        context['critical_count'] = OdooLogEntry.objects.filter(level='CRITICAL').count()
        return context


class OdooLogSourceListView(LoginRequiredMixin, ListView):
    model = OdooLogSource
    template_name = 'core/odoo_logs/sources.html'
    context_object_name = 'sources'
    login_url = '/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'odoo_logs'
        return context


class OdooLogSourceCreateView(LoginRequiredMixin, CreateView):
    model = OdooLogSource
    form_class = OdooLogSourceForm
    template_name = 'core/odoo_logs/source_form.html'
    success_url = reverse_lazy('odoo_log_sources')
    login_url = '/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'odoo_logs'
        context['action'] = 'Agregar'
        return context


class OdooLogSourceUpdateView(LoginRequiredMixin, UpdateView):
    model = OdooLogSource
    form_class = OdooLogSourceForm
    template_name = 'core/odoo_logs/source_form.html'
    success_url = reverse_lazy('odoo_log_sources')
    login_url = '/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'odoo_logs'
        context['action'] = 'Editar'
        return context


class OdooLogSourceDeleteView(LoginRequiredMixin, DeleteView):
    model = OdooLogSource
    template_name = 'core/odoo_logs/source_confirm_delete.html'
    success_url = reverse_lazy('odoo_log_sources')
    login_url = '/login/'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'odoo_logs'
        return context


class OdooLogClearView(LoginRequiredMixin, View):
    """POST: deletes all OdooLogEntry records (housekeeping)."""
    login_url = '/login/'

    def post(self, request):
        deleted, _ = OdooLogEntry.objects.all().delete()
        messages.success(request, f'Se eliminaron {deleted} entradas del log Odoo.')
        return redirect('odoo_logs')


# ── Command Log ──────────────────────────────────────────────────────────────

class CommandLogView(LoginRequiredMixin, ListView):
    model = CommandLog
    template_name = 'core/commands/list.html'
    context_object_name = 'logs'
    paginate_by = 50
    login_url = '/login/'

    def get_queryset(self):
        qs = CommandLog.objects.select_related('server', 'triggered_by')
        source = self.request.GET.get('source', '')
        server_id = self.request.GET.get('server', '').strip()
        success = self.request.GET.get('success', '')
        if source:
            qs = qs.filter(source=source)
        if server_id:
            qs = qs.filter(server_id=server_id)
        if success in ('1', '0'):
            qs = qs.filter(success=(success == '1'))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Historial de comandos'
        context['active_nav'] = 'commands'
        context['total'] = CommandLog.objects.count()
        context['manual_count'] = CommandLog.objects.filter(source=CommandLog.SOURCE_MANUAL).count()
        context['auto_count'] = CommandLog.objects.filter(source=CommandLog.SOURCE_AUTO).count()
        context['failed_count'] = CommandLog.objects.filter(success=False).count()
        context['servers'] = ServerConfig.objects.all()
        context['source_choices'] = CommandLog.SOURCE_CHOICES
        context['source_filter'] = self.request.GET.get('source', '')
        context['server_filter'] = self.request.GET.get('server', '')
        context['success_filter'] = self.request.GET.get('success', '')
        return context
