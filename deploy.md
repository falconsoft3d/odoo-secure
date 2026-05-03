# Deploy en Ubuntu — Odoo Secure

Guía paso a paso para instalar **Odoo Secure** en un servidor Ubuntu 22.04 / 24.04 usando Docker.

---

## Requisitos previos

| Componente | Versión mínima |
|---|---|
| Ubuntu | 22.04 LTS |
| Docker Engine | 24.x |
| Docker Compose v2 | 2.20+ |
| RAM | 512 MB libres |
| Disco | 2 GB libres |

---

## 1. Instalar Docker en Ubuntu

```bash
# Actualizar paquetes
sudo apt-get update && sudo apt-get upgrade -y

# Instalar dependencias
sudo apt-get install -y ca-certificates curl gnupg

# Agregar clave GPG oficial de Docker
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Agregar repositorio
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Instalar Docker Engine + Compose v2
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Verificar
docker --version
docker compose version
```

---

## 2. Clonar el repositorio

```bash
cd /opt
sudo git clone https://github.com/TU_USUARIO/odoo-secure.git
sudo chown -R $USER:$USER /opt/odoo-secure
cd /opt/odoo-secure
```

---

## 3. Configurar variables de entorno

```bash
# Copiar la plantilla
cp .env.example .env

# Editar con tus valores
nano .env
```

Valores que **debes** cambiar:

```env
# Genera una clave segura
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")

# Tu dominio o IP del servidor
ALLOWED_HOSTS=192.168.1.100

# GID del grupo docker en tu servidor
DOCKER_GID=$(getent group docker | cut -d: -f3)
```

Ejemplo rápido de una sola vez:

```bash
SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
DGID=$(getent group docker | cut -d: -f3)
IP=$(hostname -I | awk '{print $1}')

cat > .env <<EOF
SECRET_KEY=$SECRET
DEBUG=False
ALLOWED_HOSTS=$IP
DB_PATH=/app/data/db.sqlite3
HTTPS=false
DOCKER_GID=$DGID
EOF
```

---

## 4. Permisos de logs del sistema

El contenedor necesita leer `/var/log/auth.log` y el log de Odoo.

```bash
# Dar permiso de lectura al grupo 'adm' (ya montado en el contenedor)
# En Ubuntu, auth.log pertenece al grupo adm por defecto ✓

# Para los logs de Odoo (ajusta la ruta si es diferente)
sudo chmod o+r /var/log/odoo/odoo-server.log
# O añade el usuario del contenedor al grupo odoo:
# sudo usermod -aG odoo appuser
```

---

## 5. Construir y levantar el contenedor

```bash
cd /opt/odoo-secure

# Construir la imagen
docker compose build

# Levantar en segundo plano
docker compose up -d

# Verificar que está corriendo
docker compose ps
docker compose logs -f
```

---

## 6. Crear el superusuario

```bash
docker compose exec web python manage.py createsuperuser
```

Sigue las instrucciones: introduce usuario, email (opcional) y contraseña.

---

## 7. Acceder a la aplicación

Abre en el navegador:

```
http://IP_DEL_SERVIDOR:8000/login/
```

---

## 8. Configurar fuentes de log Odoo (en la UI)

1. Entra al menú **Logs Odoo → Configurar fuentes**
2. Haz clic en **Agregar fuente**
3. Introduce la ruta: `/var/log/odoo/odoo-server.log`
4. Guarda — el scheduler la leerá en el próximo ciclo (1 min)

---

## 9. Nginx como reverse proxy (opcional pero recomendado)

```bash
sudo apt-get install -y nginx
```

Crear configuración `/etc/nginx/sites-available/odoo-secure`:

```nginx
server {
    listen 80;
    server_name TU_DOMINIO_O_IP;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/odoo-secure /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Para **SSL con Let's Encrypt**:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d TU_DOMINIO.com
```

Luego actualiza `.env`:

```env
HTTPS=true
ALLOWED_HOSTS=TU_DOMINIO.com
```

Y reinicia: `docker compose up -d`

---

## 10. Auto-inicio con systemd

Crear `/etc/systemd/system/odoo-secure.service`:

```ini
[Unit]
Description=Odoo Secure
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/odoo-secure
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable odoo-secure
sudo systemctl start odoo-secure
```

---

## Comandos de mantenimiento

```bash
# Ver logs en tiempo real
docker compose logs -f web

# Reiniciar la app
docker compose restart web

# Actualizar a una nueva versión
git pull
docker compose build
docker compose up -d

# Backup de la base de datos
cp /var/lib/docker/volumes/odoo-secure_odoo_secure_data/_data/db.sqlite3 \
   /root/odoo-secure-backup-$(date +%Y%m%d).sqlite3

# Abrir shell dentro del contenedor
docker compose exec web bash

# Ejecutar migraciones manualmente
docker compose exec web python manage.py migrate
```

---

## Solución de problemas

| Problema | Causa | Solución |
|---|---|---|
| `Permission denied` en auth.log | Usuario sin acceso | `sudo usermod -aG adm appuser` |
| `docker: permission denied` | GID incorrecto | Revisar `DOCKER_GID` en `.env` |
| Métricas de CPU/RAM muestran el contenedor | `/proc` no montado | Verificar volumes en `docker-compose.yml` |
| `ALLOWED_HOSTS` error | IP/dominio no configurado | Actualizar `ALLOWED_HOSTS` en `.env` |
| Puerto 8000 ocupado | Conflicto de puertos | Cambiar `"8000:8000"` a `"8080:8000"` en `docker-compose.yml` |
