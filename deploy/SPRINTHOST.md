# Развёртывание MultiChat Hub на sprinthost.ru

Пошаговый гайд под облачный VDS Sprinthost. Конечный результат: проект работает по IP `http://<ip-сервера>/`, всё крутится в Docker, БД и Redis — внутри сети, наружу торчит только Nginx на 80-м порту.

---

## 1. Выбор тарифа VDS

В личном кабинете sprinthost.ru → раздел **«Облачные серверы»** → **«Создать сервер»**.

**Минимальные параметры для MultiChat Hub:**

| Параметр | Минимум | Рекомендуется |
|---|---|---|
| CPU | 2 ядра | 2–4 ядра |
| RAM | 4 ГБ | 4–8 ГБ |
| Диск | 30 ГБ SSD | 40–60 ГБ SSD |
| Канал | 100 Мбит/с | 100 Мбит/с |
| ОС | Ubuntu 22.04 LTS | **Ubuntu 24.04 LTS** или Debian 12 |

Образ выбираем **«чистый» без панели управления** — никаких ISPmanager/cPanel не нужно, всё ставим через Docker.

После создания на email и в панели sprinthost появятся:
- IP-адрес сервера, например `185.xx.xx.xx`
- Логин root (или предложат свой)
- Сгенерированный пароль для SSH

---

## 2. Первое подключение по SSH

С локальной машины (macOS/Windows/Linux):

```bash
ssh root@185.xx.xx.xx
```

При первом подключении подтвердить fingerprint и ввести пароль из письма sprinthost.

**Сразу сменить пароль root:**

```bash
passwd
```

Дальше — рекомендую добавить свой SSH-ключ и отключить вход по паролю, но это можно пропустить, если сервер только для диплома.

```bash
mkdir -p ~/.ssh
echo "<ваш-публичный-ключ из ~/.ssh/id_ed25519.pub>" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

---

## 3. Базовая подготовка системы

```bash
apt update && apt upgrade -y
apt install -y curl git ufw htop nano
```

**Открыть только нужные порты в firewall:**

```bash
ufw allow OpenSSH
ufw allow 80/tcp
# ufw allow 443/tcp   # включить, когда появится HTTPS
ufw --force enable
```

Проверка:

```bash
ufw status
```

В панели sprinthost дополнительный сетевой firewall обычно по умолчанию открыт на всё — этого достаточно, потому что мы сами ограничили через `ufw` на самом сервере. Если в панели есть «Группы безопасности» — открыть в них TCP 22, 80 (и 443 на будущее).

---

## 4. Установка Docker + Docker Compose

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
docker compose version
```

Должно вывести что-то вроде `Docker Compose version v2.31.x`. Если нет — установить плагин:

```bash
apt install -y docker-compose-plugin
```

---

## 5. Заливка проекта на сервер

**Вариант А — через git** (если репозиторий уже залит на GitHub/GitLab):

```bash
mkdir -p /opt
cd /opt
git clone https://github.com/<your>/multichat.git multichat
cd multichat
```

**Вариант Б — через `scp` с локальной машины** (если репозитория нет):

С локальной машины:

```bash
cd /Users/p4vuk/Desktop/Димплом
tar --exclude='node_modules' --exclude='.next' --exclude='__pycache__' \
    --exclude='.git' --exclude='media' --exclude='staticfiles' \
    -czf /tmp/multichat.tar.gz \
    backend saa-s-dashboard-development deploy demo-site
scp /tmp/multichat.tar.gz root@185.xx.xx.xx:/opt/
```

На сервере:

```bash
cd /opt
mkdir multichat && tar -xzf multichat.tar.gz -C multichat
cd multichat
```

---

## 6. Заполнение production-окружения

```bash
cp deploy/.env.prod.example deploy/.env.prod
nano deploy/.env.prod
```

**Что обязательно заменить** (подставить реальный IP сервера от sprinthost):

```dotenv
DEBUG=0

# Сгенерировать локально: python3 -c "import secrets; print(secrets.token_urlsafe(50))"
SECRET_KEY=ВСТАВИТЬ_СГЕНЕРИРОВАННЫЙ_КЛЮЧ

ALLOWED_HOSTS=185.xx.xx.xx,localhost
CSRF_TRUSTED_ORIGINS=http://185.xx.xx.xx
CORS_ALLOWED_ORIGINS=http://185.xx.xx.xx
FRONTEND_URL=http://185.xx.xx.xx

DB_NAME=multichat
DB_USER=multichat_user
# Длинный случайный пароль — можно сгенерировать тем же secrets.token_urlsafe
DB_PASSWORD=ВСТАВИТЬ_ДЛИННЫЙ_ПАРОЛЬ

REDIS_URL=redis://redis:6379/0

# SMTP — можно перенести значения из dev .env (системная почта)
EMAIL_HOST=smtp.mail.ru
EMAIL_PORT=465
EMAIL_USE_SSL=1
EMAIL_USE_TLS=0
EMAIL_HOST_USER=ваш_логин@mail.ru
EMAIL_HOST_PASSWORD=ваш_smtp_пароль_приложения
DEFAULT_FROM_EMAIL=ваш_логин@mail.ru

INVITE_TOKEN_EXPIRE_HOURS=48
RESET_TOKEN_EXPIRE_HOURS=1

# Оставить пустым — фронт пойдёт на тот же origin через nginx
NEXT_PUBLIC_API_URL=
```

Сохранить (`Ctrl+O`, `Enter`, `Ctrl+X`).

---

## 7. Запуск стека

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d --build
```

Первый билд займёт 5–10 минут (sprinthost обычно даёт хороший канал, но билд фронта Next.js — это всё равно несколько минут).

Когда команда отработает, посмотреть статус:

```bash
docker compose -f deploy/docker-compose.prod.yml ps
```

Должно быть `Up` у всех сервисов: `db`, `redis`, `web`, `celery`, `celery-beat`, `frontend`, `nginx`.

Если `web` упал в `Restarting` — посмотреть логи:

```bash
docker compose -f deploy/docker-compose.prod.yml logs web --tail 100
```

---

## 8. Поднять права администратора Django admin

По умолчанию `create_default_admin` ставит роль `admin` приложения, но не Django-флаги. Выполнить **один раз**:

```bash
docker compose -f deploy/docker-compose.prod.yml exec web python manage.py shell <<'PY'
from django.contrib.auth import get_user_model
U = get_user_model()
u = U.objects.get(email='admin@admin.com')
u.is_staff = True
u.is_superuser = True
u.set_password('ВАШ_НОВЫЙ_СИЛЬНЫЙ_ПАРОЛЬ_АДМИНА')
u.save()
print('OK')
PY
```

---

## 9. Проверка

С локального ноутбука открыть в браузере:

- `http://185.xx.xx.xx/` — должен открыться экран входа MultiChat
- `http://185.xx.xx.xx/admin/login/` — Django admin (логин `admin@admin.com` + пароль, который вы поставили выше)
- `http://185.xx.xx.xx/api/schema/swagger/` — Swagger API

Зайти, создать сайт, скопировать код виджета (`<script src="...">`) и вставить его на любой статический HTML. Подключение к WebSocket-уведомлениям должно работать.

---

## 10. Бэкап БД и снапшоты sprinthost

**Бэкап PostgreSQL вручную:**

```bash
mkdir -p /opt/multichat/backups
docker compose -f /opt/multichat/deploy/docker-compose.prod.yml exec -T db \
  pg_dump -U multichat_user multichat > /opt/multichat/backups/db_$(date +%F_%H%M).sql
```

Удобно добавить в cron:

```bash
crontab -e
# Каждый день в 04:00
0 4 * * * cd /opt/multichat && docker compose -f deploy/docker-compose.prod.yml exec -T db pg_dump -U multichat_user multichat > backups/db_$(date +\%F).sql
```

**Снапшоты Sprinthost:**

В панели VDS sprinthost есть кнопка «Снапшот» (или «Создать образ»). Рекомендую сделать снапшот сразу после успешного первого запуска — будет точка отката. Стоит небольших копеек или включено в тариф.

---

## 11. Подключение домена через Sprinthost DNS

Когда появится домен (купленный у sprinthost или внешнего регистратора):

**Если домен у sprinthost:**
1. Личный кабинет → «Домены» → выбрать домен → «DNS-записи»
2. Добавить A-запись: `@ → 185.xx.xx.xx` и `www → 185.xx.xx.xx`
3. TTL по умолчанию (3600 с).

**Если домен у другого регистратора:**
1. У регистратора прописать NS-серверы sprinthost (обычно `ns1.sprinthost.ru`, `ns2.sprinthost.ru`), либо
2. Просто добавить A-записи на IP сервера sprinthost.

**После того как DNS пропагнулся** (5–60 минут, проверить `dig example.com`):

На сервере поправить `deploy/.env.prod`:

```dotenv
ALLOWED_HOSTS=example.com,www.example.com,185.xx.xx.xx
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
CORS_ALLOWED_ORIGINS=https://example.com
FRONTEND_URL=https://example.com
NEXT_PUBLIC_API_URL=
```

Перезалить фронт-образ (т.к. NEXT_PUBLIC_API_URL в нём вшит — но мы оставили пустым, так что пересборка не обязательна, если ходим через тот же origin):

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d --build web
```

---

## 12. Подключение HTTPS (Let's Encrypt)

Когда домен подключён и работает по HTTP:

```bash
apt install -y certbot

# Остановим nginx-контейнер на момент выдачи серта (метод --standalone)
docker compose -f /opt/multichat/deploy/docker-compose.prod.yml stop nginx

certbot certonly --standalone -d example.com -d www.example.com \
  --email admin@example.com --agree-tos --no-eff-email

# Сертификаты лягут в /etc/letsencrypt/live/example.com/
```

Открыть `/opt/multichat/deploy/nginx/default.conf` и добавить блок:

```nginx
server {
    listen 443 ssl http2;
    server_name example.com www.example.com;
    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
    # ... содержимое из существующего блока server {listen 80;}
}

server {
    listen 80;
    server_name example.com www.example.com;
    return 301 https://$host$request_uri;
}
```

Открыть `/opt/multichat/deploy/docker-compose.prod.yml`, в сервисе `nginx`:

```yaml
nginx:
  ports:
    - "80:80"
    - "443:443"     # раскомментировать
  volumes:
    - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
    - static_volume:/var/www/static:ro
    - media_volume:/var/www/media:ro
    - /etc/letsencrypt:/etc/letsencrypt:ro    # добавить
```

В `ufw`:

```bash
ufw allow 443/tcp
```

Перезапуск:

```bash
docker compose -f deploy/docker-compose.prod.yml up -d nginx
```

Авто-обновление сертификата:

```bash
crontab -e
# Раз в неделю проверяем продление, перезапускаем nginx-контейнер
0 3 * * 0 certbot renew --quiet --pre-hook "docker compose -f /opt/multichat/deploy/docker-compose.prod.yml stop nginx" --post-hook "docker compose -f /opt/multichat/deploy/docker-compose.prod.yml start nginx"
```

---

## 13. Типовые ошибки и их решения

| Симптом | Причина | Что делать |
|---|---|---|
| `502 Bad Gateway` от nginx | Бэкенд/фронт ещё стартует или упал | `docker compose ... logs web` — посмотреть стек ошибки |
| `Bad Request (400)` на admin | `ALLOWED_HOSTS` не содержит IP/домена | Добавить в `.env.prod`, перезапустить `web` |
| `CSRF verification failed` в админке | `CSRF_TRUSTED_ORIGINS` не содержит origin | Добавить полный URL c протоколом |
| Виджет не подключается с внешнего сайта | CORS-блок | `WidgetCORSMiddleware` уже разрешает всё для `/api/widget/*`, проверить логи nginx и ответ `OPTIONS` |
| WebSocket не апгрейдится | `proxy_set_header Upgrade` отсутствует | Проверить `location /ws/` в nginx-конфиге |
| Контейнер `web` крашится с `OperationalError` | БД ещё не готова | Добавлен healthcheck — но первый старт может занять 20–30 с, перезапустить |
| Письма не уходят | Неверные SMTP-данные | mail.ru требует **пароль приложения**, не пароль от ящика |

Логи nginx:

```bash
docker compose -f deploy/docker-compose.prod.yml logs nginx --tail 200
```

Логи бэкенда (включая Celery):

```bash
docker compose -f deploy/docker-compose.prod.yml logs -f web celery celery-beat
```

---

## 14. Что включает Sprinthost само

- Бэкап диска VDS — обычно раз в сутки (зависит от тарифа). Это **не** замена `pg_dump` (восстановление на уровне всего диска, не точечное).
- Мониторинг RAM/CPU/Network в панели — удобно посмотреть, не упирается ли стек в лимиты.
- KVM-консоль (доступ к серверу даже при упавшей сети) — пригодится, если случайно отрезали себя через `ufw`.
- Поддержка — отвечают на русском, тикеты решаются быстро. Если уперлись в сеть/диск — пишите в тикет.

---

## Чек-лист сдачи

- [ ] VDS создан, ОС обновлена, ufw настроен
- [ ] Docker + compose установлены, `docker compose version` отвечает
- [ ] Проект залит в `/opt/multichat`
- [ ] `deploy/.env.prod` заполнен реальными секретами
- [ ] `docker compose ... ps` показывает все сервисы `Up`
- [ ] `http://IP/` открывает страницу входа MultiChat
- [ ] `http://IP/admin/` пускает по новому паролю
- [ ] Виджет встроен на тестовый HTML и принимает сообщения
- [ ] WebSocket-уведомления работают (карточка в Kanban обновляется без F5)
- [ ] Снапшот VDS сделан, бэкап `pg_dump` сделан
- [ ] Дефолтный пароль `admin@admin.com / admin` сменён на сильный
