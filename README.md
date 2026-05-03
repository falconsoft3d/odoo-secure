# Odoo Secure

Aplicación Django para monitorear y gestionar la seguridad de servidores Odoo.

---

## Actualizar en producción (Docker)

```bash
cd /opt/odoo-secure

# 1. Descargar cambios
git pull

# 2. Reconstruir la imagen
docker compose build

# 3. Aplicar migraciones de BD
docker compose run --rm web python manage.py migrate

# 4. Reiniciar el contenedor
docker compose up -d
```

---

## Comandos útiles

```bash
# Ver logs en tiempo real
docker compose logs -f web

# Reiniciar solo la app
docker compose restart web

# Abrir shell dentro del contenedor
docker compose exec web bash

# Ejecutar migraciones manualmente
docker compose exec web python manage.py migrate

# Crear superusuario
docker compose exec web python manage.py createsuperuser

# Backup de la base de datos
cp /var/lib/docker/volumes/odoo-secure_odoo_secure_data/_data/db.sqlite3 \
   ~/odoo-secure-backup-$(date +%Y%m%d).sqlite3
```

---

## Desarrollo local

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Ver [deploy.md](deploy.md) para la guía completa de instalación en Ubuntu.
