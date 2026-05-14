# Деплой MultiChat Hub на VPS

Один сервер, всё в Docker. Без домена — по IP. HTTPS добавляется отдельным шагом, когда появится доменное имя.

> Для конкретных хостингов есть пошаговые гайды: [**TIMEWEB.md**](TIMEWEB.md) — Timeweb Cloud (рекомендуется), [SPRINTHOST.md](SPRINTHOST.md) — Sprinthost VDS.

## Что разворачивается

```
                      ┌─────────────────┐
   :80  HTTP   ───►   │      nginx      │
                      └────┬───────┬────┘
                           │       │
              /api, /admin │       │ / (всё остальное)
              /ws, /static │       │
              /media       │       │
                           ▼       ▼
                  ┌────────────┐ ┌─────────────┐
                  │  Django    │ │  Next.js    │
                  │  Daphne    │ │  standalone │
                  │  :8000     │ │  :3000      │
                  └────┬───────┘ └─────────────┘
                       │
                ┌──────┴────────┬──────────────┐
                ▼               ▼              ▼
           ┌─────────┐   ┌────────────┐  ┌──────────┐
           │ Postgres│   │   Redis    │  │  Celery  │
           │  :5432  │   │   :6379    │  │  + beat  │
           └─────────┘   └────────────┘  └──────────┘
```

Все сервисы — внутри одной docker-сети. Наружу торчит только nginx на :80.

## Требования к серверу

- Linux (Debian/Ubuntu 22.04+)
- Docker Engine 24+ и Docker Compose Plugin v2
- 2 CPU / 4 ГБ RAM минимум
- Порт 80 открыт

## Шаги развёртывания

### 1. Залить проект на сервер

```bash
git clone <repo-url> /opt/multichat
cd /opt/multichat
```

### 2. Заполнить production-окружение

```bash
cp deploy/.env.prod.example deploy/.env.prod
```

Открыть `deploy/.env.prod` и обязательно заменить:

- `SECRET_KEY` — сгенерировать новый:
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(50))"
  ```
- `ALLOWED_HOSTS` — IP сервера (`1.2.3.4,localhost`)
- `CSRF_TRUSTED_ORIGINS` — `http://1.2.3.4`
- `CORS_ALLOWED_ORIGINS` — `http://1.2.3.4`
- `FRONTEND_URL` — `http://1.2.3.4`
- `DB_PASSWORD` — длинный случайный пароль
- `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` — рабочие SMTP-учётки (можно скопировать из dev `.env`, если они уже работают)
- `NEXT_PUBLIC_API_URL` — оставить пустым, если фронт и бэк ходят через один и тот же nginx

### 3. Собрать и запустить

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d --build
```

При первом запуске:
- Билды контейнеров (~5–10 минут на VPS)
- `entrypoint.sh` бэкенда сам выполнит `migrate` и `collectstatic`
- `create_default_admin` создаст администратора `admin@admin.com / admin`, если в БД нет пользователей

### 4. Поднять права администратора для входа в Django admin

По умолчанию `create_default_admin` ставит роль `admin` приложения, но не Django-флаги. Один раз выполнить:

```bash
docker compose -f deploy/docker-compose.prod.yml exec web python manage.py shell <<'PY'
from django.contrib.auth import get_user_model
U = get_user_model()
u = U.objects.get(email='admin@admin.com')
u.is_staff = True; u.is_superuser = True
u.set_password('СВОЙ_СИЛЬНЫЙ_ПАРОЛЬ')
u.save()
PY
```

### 5. Проверить

- `http://1.2.3.4/` — фронт (страница входа)
- `http://1.2.3.4/admin/` — Django admin
- `http://1.2.3.4/api/schema/swagger/` — OpenAPI

## Управление

| Действие | Команда |
|---|---|
| Логи всех сервисов | `docker compose -f deploy/docker-compose.prod.yml logs -f` |
| Логи одного сервиса | `docker compose -f deploy/docker-compose.prod.yml logs -f web` |
| Рестарт после правок | `docker compose -f deploy/docker-compose.prod.yml up -d --build` |
| Остановить всё | `docker compose -f deploy/docker-compose.prod.yml down` |
| Снести всё (включая БД!) | `docker compose -f deploy/docker-compose.prod.yml down -v` |
| Бэкап БД | `docker compose -f deploy/docker-compose.prod.yml exec db pg_dump -U $DB_USER $DB_NAME > backup_$(date +%F).sql` |
| Рестор БД | `cat backup.sql \| docker compose -f deploy/docker-compose.prod.yml exec -T db psql -U $DB_USER $DB_NAME` |

## Когда появится домен

1. Указать A-запись домена на IP сервера.
2. Поправить в `deploy/.env.prod`:
   ```
   ALLOWED_HOSTS=example.com,www.example.com
   CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
   CORS_ALLOWED_ORIGINS=https://example.com
   FRONTEND_URL=https://example.com
   NEXT_PUBLIC_API_URL=https://example.com
   ```
3. Перевыпустить фронт-образ:
   ```bash
   docker compose -f deploy/docker-compose.prod.yml up -d --build frontend
   ```

## Когда добавляется HTTPS (Let's Encrypt)

Простейший вариант — добавить в стек `certbot` и `nginx-proxy` или `caddy`. Минимальная схема через `certbot`:

1. Установить certbot на хост: `apt install certbot`
2. Получить сертификат:
   ```bash
   certbot certonly --webroot -w /var/www/letsencrypt -d example.com
   ```
3. Смонтировать `/etc/letsencrypt` в nginx-контейнер, добавить блок `server { listen 443 ssl; ... }` в `deploy/nginx/default.conf`.

Готовый pre-baked вариант — `jwilder/nginx-proxy` + `jrcs/letsencrypt-nginx-proxy-companion` (отдельный шаблон сделаю по запросу).

## Безопасность чек-лист (после первого деплоя)

- [ ] Новый `SECRET_KEY` (не из примера)
- [ ] Новый `DB_PASSWORD`
- [ ] Сменён дефолтный пароль `admin@admin.com`
- [ ] `DEBUG=0` в `.env.prod`
- [ ] `ALLOWED_HOSTS` не содержит `*`
- [ ] Порт 80 закрыт от лишних подключений на уровне облака/firewall, открыт только HTTP
- [ ] Регулярные бэкапы БД (`pg_dump` по cron)
- [ ] При появлении домена — включить HTTPS и `SECURE_SSL_REDIRECT=True` в settings (раскомментировать `:443` в compose)
