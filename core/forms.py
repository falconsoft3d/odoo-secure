from django import forms
from .models import ServerConfig, OdooLogSource


class ServerConfigForm(forms.ModelForm):
    class Meta:
        model = ServerConfig
        fields = ['name', 'url', 'restart_command', 'check_interval', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white '
                         'placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition',
                'placeholder': 'Ej: Producción EU-1',
            }),
            'url': forms.URLInput(attrs={
                'class': 'w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white '
                         'placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition',
                'placeholder': 'https://odoo.miempresa.com/web/health',
            }),
            'restart_command': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white font-mono '
                         'placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition resize-none',
                'placeholder': 'docker restart odoo',
            }),
            'check_interval': forms.NumberInput(attrs={
                'min': 1,
                'max': 1440,
                'class': 'w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white '
                         'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 rounded bg-gray-800 border-gray-600 text-brand-600 '
                         'focus:ring-brand-500 focus:ring-offset-gray-900',
            }),
        }
        labels = {
            'name': 'Nombre del servidor',
            'url': 'URL de comprobación',
            'restart_command': 'Comando de reinicio',
            'check_interval': 'Intervalo de chequeo (minutos)',
            'is_active': 'Monitoreo activo',
        }


_INPUT = (
    'w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white '
    'placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500 '
    'focus:border-transparent transition'
)


class OdooLogSourceForm(forms.ModelForm):
    class Meta:
        model = OdooLogSource
        fields = ['name', 'log_path', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': _INPUT,
                'placeholder': 'Ej: Producción Odoo',
            }),
            'log_path': forms.TextInput(attrs={
                'class': _INPUT + ' font-mono',
                'placeholder': '/var/log/odoo/odoo-server.log',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 rounded bg-gray-800 border-gray-600 text-brand-600 '
                         'focus:ring-brand-500 focus:ring-offset-gray-900',
            }),
        }
        labels = {
            'name': 'Nombre',
            'log_path': 'Ruta del archivo de log',
            'is_active': 'Activo',
        }
