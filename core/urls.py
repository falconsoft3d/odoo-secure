from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.redirect_root, name='root'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    # Servidores
    path('servers/', views.ServerConfigListView.as_view(), name='servers'),
    path('servers/add/', views.ServerConfigCreateView.as_view(), name='server_add'),
    path('servers/<int:pk>/edit/', views.ServerConfigUpdateView.as_view(), name='server_edit'),
    path('servers/<int:pk>/delete/', views.ServerConfigDeleteView.as_view(), name='server_delete'),
    path('servers/<int:pk>/history/', views.ServerHistoryView.as_view(), name='server_history'),
    path('servers/<int:pk>/restart/', views.ServerManualRestartView.as_view(), name='server_restart'),
    # Seguridad
    path('security/', views.SecurityLogView.as_view(), name='security'),
    # Sistema
    path('system/', views.SystemStatsView.as_view(), name='system'),
    path('system/metrics/', views.MetricsChartView.as_view(), name='system_metrics'),
    # Logs Odoo
    path('odoo-logs/', views.OdooLogListView.as_view(), name='odoo_logs'),
    path('odoo-logs/sources/', views.OdooLogSourceListView.as_view(), name='odoo_log_sources'),
    path('odoo-logs/sources/add/', views.OdooLogSourceCreateView.as_view(), name='odoo_log_source_add'),
    path('odoo-logs/sources/<int:pk>/edit/', views.OdooLogSourceUpdateView.as_view(), name='odoo_log_source_edit'),
    path('odoo-logs/sources/<int:pk>/delete/', views.OdooLogSourceDeleteView.as_view(), name='odoo_log_source_delete'),
    path('odoo-logs/clear/', views.OdooLogClearView.as_view(), name='odoo_log_clear'),
    # Historial de comandos
    path('commands/', views.CommandLogView.as_view(), name='commands'),
    # Historial de cron jobs
    path('scheduler/', views.SchedulerLogView.as_view(), name='scheduler_log'),
    path('scheduler/run/<str:job_id>/', views.RunJobView.as_view(), name='run_job'),
]
