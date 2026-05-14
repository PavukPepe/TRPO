# Развёртывание MultiChat Hub на Timeweb Cloud

Пошаговый гайд под облачные серверы [timeweb.cloud](https://timeweb.cloud). На выходе: проект работает по IP `http://<ip-сервера>/`, всё в Docker, наружу торчит только Nginx на 80-м порту.

> Главное преимущество Timeweb для нашего случая — есть готовый образ **«Ubuntu 22.04 + Docker»**, поэтому установка Docker отдельным шагом не нужна. Также снапшоты бесплатные.

---

## 1. Регистрация и пополнение баланса

1. Зайти на [timeweb.cloud](https://timeweb.cloud) → «Войти / Регистрация»
2. Зарегистрироваться (телефон + email)
3. В личном кабинете: **Финансы → Пополнить баланс**
   - Оплата: карты «Мир», Visa/MC российских банков, СБП, расчётный счёт для юр.лица
   - Минимум ~500 ₽, чтобы хватило на месяц с запасом
4. Если есть промокод — ввести в разделе **Финансы → Промокоды** (бывают скидки 30–50 % на первый месяц)

---

## 2. Создание облачного сервера

В кабинете: **Облачные серверы → Создать сервер**.

### Конфигурация

| Параметр | Значение |
|---|---|
| Тип | **Виртуальный сервер** |
| Локация | **Москва** или **Санкт-Петербург** (любой) |
| Тариф | **Cloud Server 2x4** |
| CPU | 2 vCPU |
| RAM | 4 ГБ |
| Диск | 60 ГБ NVMe |
| Цена | ~490 ₽/мес (или ~0,67 ₽/час) |
| ОС / Образ | **Marketplace → Docker** (на базе Ubuntu 22.04) |
| Дополнительный IP | Не нужно |
| Бэкапы | **Включить ежедневные** (опционально, ~100 ₽/мес) |
| SSH-ключ | Загрузить свой публичный ключ (см. ниже) или оставить «Пароль» |

### Про SSH-ключ (рекомендуется)

С локальной машины:

```bash
# Если ключа ещё нет — сгенерировать
ssh-keygen -t ed25519 -C "multichat-deploy"
# Скопировать публичную часть
cat ~/.ssh/id_ed25519.pub
```

В Timeweb: **SSH-ключи → Добавить ключ** → вставить содержимое `id_ed25519.pub`. При создании сервера выбрать этот ключ — root-пароль создавать не понадобится.

### Создание

Нажать «Создать сервер». Через 1–2 минуты сервер появится в списке в статусе «Включён», с IP-адресом и (если без SSH-ключа) сгенерированным паролем root в письме на email.

---

## 3. Первое подключение

С локального компьютера:

```bash
ssh root@<ip-сервера>
```

При выборе образа «Docker» уже установлено:
- Ubuntu 22.04 LTS
- Docker Engine 24+
- Docker Compose v2
- `git`, `curl`, `htop`, `nano`

Проверить:

```bash
docker --version
docker compose version
```

Должно вывести версии без ошибок.

> Если выбирали обычный образ Ubuntu без Docker — выполнить:
> ```bash
> curl -fsSL https://get.docker.com | sh
> systemctl enable --now docker
> ```

---

## 4. Базовая защита (firewall)

```bash
apt update && apt upgrade -y
apt install -y ufw
ufw allow OpenSSH
ufw allow 80/tcp
# ufw allow 443/tcp   # включить, когда появится HTTPS
ufw --force enable
ufw status
```

> **Важно:** у Timeweb есть свой сетевой firewall в панели (раздел сервера → **Сеть → Firewall**). По умолчанию он открыт целиком. Можно настроить и его — оставить только TCP 22 и 80. На уровне сервера `ufw` всё равно нужен.

Сменить root-пароль (если входили по нему):

```bash
passwd
```

---

## 5. Заливка проекта на сервер

### Вариант А — через git (предпочтительный)

Если репозиторий есть на GitHub/GitLab:

```bash
mkdir -p /opt
cd /opt
git clone https://github.com/<your>/multichat.git multichat
cd multichat
```

### Вариант Б — через SFTP с локальной машины

Если репозитория нет — упаковать локально и закинуть:

С локальной машины:

```bash
cd /Users/p4vuk/Desktop/Димплом
tar --exclude='node_modules' --exclude='.next' --exclude='__pycache__' \
    --exclude='.git' --exclude='media' --exclude='staticfiles' \
    -czf /tmp/multichat.tar.gz \
    backend saa-s-dashboard-development deploy demo-site

scp /tmp/multichat.tar.gz root@<ip-сервера>:/opt/
```

На сервере:

```bash
cd /opt
mkdir multichat
tar xzf multichat.tar.gz -C multichat
cd multichat
```

Альтернативно через визуальный SFTP — **FileZilla** / **Cyberduck** / **WinSCP**:
- Протокол: SFTP, порт 22, хост — IP сервера, логин `root`, пароль (или ключ)
- Перетащить папку проекта в `/opt/multichat/`

---

## 6. Заполнение production-окружения

```bash
cp deploy/.env.prod.example deploy/.env.prod
nano deploy/.env.prod
```

Подставить реальный IP сервера, выданный Timeweb:

```dotenv
DEBUG=0

# Сгенерировать локально: python3 -c "import secrets; print(secrets.token_urlsafe(50))"
SECRET_KEY=ВСТАВИТЬ_СГЕНЕРИРОВАННЫЙ_КЛЮЧ

ALLOWED_HOSTS=<ip-сервера>,localhost
CSRF_TRUSTED_ORIGINS=http://<ip-сервера>
CORS_ALLOWED_ORIGINS=http://<ip-сервера>
FRONTEND_URL=http://<ip-сервера>

DB_NAME=multichat
DB_USER=multichat_user
DB_PASSWORD=ВСТАВИТЬ_ДЛИННЫЙ_ПАРОЛЬ

REDIS_URL=redis://redis:6379/0

# SMTP — переносим рабочие значения из своего dev .env (mail.ru / smtp.mail.ru)
EMAIL_HOST=smtp.mail.ru
EMAIL_PORT=465
EMAIL_USE_SSL=1
EMAIL_USE_TLS=0
EMAIL_HOST_USER=ваш_логин@mail.ru
EMAIL_HOST_PASSWORD=ваш_пароль_приложения_mail_ru
DEFAULT_FROM_EMAIL=ваш_логин@mail.ru

INVITE_TOKEN_EXPIRE_HOURS=48
RESET_TOKEN_EXPIRE_HOURS=1

# Пусто — фронт пойдёт через тот же nginx
NEXT_PUBLIC_API_URL=
```

Сохранить (`Ctrl+O`, `Enter`, `Ctrl+X`).

---

## 7. Запуск стека

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d --build
```

Первый билд занимает 5–10 минут (Timeweb даёт хороший сетевой канал, скачивание базовых образов идёт быстро).

Когда команда завершится — проверить статус:

```bash
docker compose -f deploy/docker-compose.prod.yml ps
```

Все 7 сервисов должны быть в статусе `Up` / `healthy`: `db`, `redis`, `web`, `celery`, `celery-beat`, `frontend`, `nginx`.

Если что-то в `Restarting` — посмотреть логи:

```bash
docker compose -f deploy/docker-compose.prod.yml logs <имя-сервиса> --tail 100
```

---

## 8. Поднять права администратора Django

`create_default_admin` создаёт пользователя `admin@admin.com / admin` с ролью админа приложения, но без Django-флагов `is_staff`/`is_superuser`. Выполнить один раз:

```bash
docker compose -f deploy/docker-compose.prod.yml exec web python manage.py shell <<'PY'
from django.contrib.auth import get_user_model
U = get_user_model()
u = U.objects.get(email='admin@admin.com')
u.is_staff = True
u.is_superuser = True
u.set_password('ВАШ_НОВЫЙ_СИЛЬНЫЙ_ПАРОЛЬ')
u.save()
print('OK')
PY
```

---

## 9. Проверка

В браузере (с локальной машины):

- `http://<ip-сервера>/` — экран входа MultiChat
- `http://<ip-сервера>/admin/login/` — Django admin (логин `admin@admin.com`, пароль из шага 8)
- `http://<ip-сервера>/api/schema/swagger/` — Swagger UI

Зайти в кабинет, создать сайт, скопировать код виджета `<script src="...">`, вставить в любую тестовую HTML-страницу (можно открыть локальный `demo-site/index.html`, поправив `data-site-id`). Виджет должен подключиться, сообщения должны падать в Kanban в реальном времени без перезагрузки.

---

## 10. Бэкап БД

### Снапшоты Timeweb (на уровне диска)

В кабинете: сервер → **Бэкапы → Создать снапшот**. Бесплатно. Рекомендую сделать снапшот сразу после успешной первой настройки — будет точка отката.

Также можно включить **ежедневные автобэкапы** в настройках сервера (доп. ~100 ₽/мес, хранится 7 копий).

### Дамп БД (точечный)

Снапшот диска восстанавливает весь сервер целиком — это «тяжёлый» вариант. Для точечного бэкапа базы:

```bash
mkdir -p /opt/multichat/backups

docker compose -f /opt/multichat/deploy/docker-compose.prod.yml exec -T db \
  pg_dump -U multichat_user multichat > /opt/multichat/backups/db_$(date +%F_%H%M).sql
```

Автоматизировать через cron:

```bash
crontab -e
```

Добавить строку (ежедневно в 04:00):

```cron
0 4 * * * cd /opt/multichat && docker compose -f deploy/docker-compose.prod.yml exec -T db pg_dump -U multichat_user multichat > backups/db_$(date +\%F).sql
```

---

## 11. Подключение домена через Timeweb DNS

Timeweb — ещё и регистратор. Купить домен можно прямо в кабинете: **Домены → Зарегистрировать**.

### Если домен у Timeweb

1. **Домены → ваш домен → Управление зоной**
2. Добавить A-запись: `@ → <ip-сервера>`, TTL 3600
3. Добавить A-запись: `www → <ip-сервера>`, TTL 3600
4. Подождать 5–60 минут, проверить:

   ```bash
   dig example.com +short
   ```

   Должен вернуть IP сервера.

### Если домен у другого регистратора

Два способа:
- **NS-серверы Timeweb:** у регистратора прописать `ns1.timeweb.ru`, `ns2.timeweb.ru`, дальше управлять DNS через Timeweb.
- **A-записи напрямую:** просто добавить A-записи у регистратора.

### После того как DNS подхватился

Поправить `deploy/.env.prod`:

```dotenv
ALLOWED_HOSTS=example.com,www.example.com,<ip-сервера>
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
CORS_ALLOWED_ORIGINS=https://example.com
FRONTEND_URL=https://example.com
NEXT_PUBLIC_API_URL=
```

Перезапустить бэкенд (фронт пересобирать не надо, т.к. `NEXT_PUBLIC_API_URL` пустой и идёт через тот же origin):

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d web
```

---

## 12. Подключение HTTPS (Let's Encrypt)

Когда домен привязан и работает по HTTP:

```bash
apt install -y certbot

docker compose -f /opt/multichat/deploy/docker-compose.prod.yml stop nginx

certbot certonly --standalone -d example.com -d www.example.com \
  --email admin@example.com --agree-tos --no-eff-email
```

Сертификаты лягут в `/etc/letsencrypt/live/example.com/`.

Открыть `/opt/multichat/deploy/nginx/default.conf` и добавить блок 443 (поверх существующего блока `:80`):

```nginx
server {
    listen 80;
    server_name example.com www.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name example.com www.example.com;

    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    # ... всё содержимое локаций из существующего блока :80
}
```

В `/opt/multichat/deploy/docker-compose.prod.yml` в сервисе `nginx`:

```yaml
nginx:
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
    - static_volume:/var/www/static:ro
    - media_volume:/var/www/media:ro
    - /etc/letsencrypt:/etc/letsencrypt:ro
```

В `ufw`:

```bash
ufw allow 443/tcp
```

И в Timeweb-firewall в панели — открыть TCP 443. Перезапуск:

```bash
docker compose -f deploy/docker-compose.prod.yml up -d nginx
```

Авто-продление по cron:

```cron
0 3 * * 0 certbot renew --quiet --pre-hook "docker compose -f /opt/multichat/deploy/docker-compose.prod.yml stop nginx" --post-hook "docker compose -f /opt/multichat/deploy/docker-compose.prod.yml start nginx"
```

---

## 13. Особенности Timeweb, которые пригодятся

| Фича | Где в кабинете | Зачем |
|---|---|---|
| Веб-консоль (KVM) | Сервер → Консоль | Зайти на сервер, если случайно отрезали себя через ufw |
| Снапшоты | Сервер → Бэкапы | Бесплатная точка отката |
| Метрики CPU/RAM/диск | Сервер → Графики | Понять, упирается ли стек в лимиты |
| Сетевой firewall | Сервер → Сеть → Firewall | Дополнительный слой защиты сверх ufw |
| Базовая защита от DDoS | Включена по умолчанию | Бесплатно, фильтрует L3/L4 атаки |
| Изменение тарифа | Сервер → Настройки → Тариф | Можно увеличить CPU/RAM, если упрётесь, без переустановки |
| Поддержка | Чат в правом нижнем углу | Русскоязычная, отвечают быстро |
| API | Кабинет → API | Если захочется автоматизировать деплой |

---

## 14. Управление контейнерами

| Действие | Команда |
|---|---|
| Логи всех сервисов | `docker compose -f deploy/docker-compose.prod.yml logs -f` |
| Логи одного сервиса | `docker compose -f deploy/docker-compose.prod.yml logs -f web` |
| Перезапуск после правок кода | `docker compose -f deploy/docker-compose.prod.yml up -d --build` |
| Остановить всё | `docker compose -f deploy/docker-compose.prod.yml down` |
| Снести с данными (БД сотрётся!) | `docker compose -f deploy/docker-compose.prod.yml down -v` |
| Войти внутрь контейнера | `docker compose -f deploy/docker-compose.prod.yml exec web bash` |
| Применить миграции вручную | `docker compose -f deploy/docker-compose.prod.yml exec web python manage.py migrate` |

---

## 15. Типовые ошибки и их решения

| Симптом | Причина | Решение |
|---|---|---|
| `502 Bad Gateway` от nginx | Бэкенд/фронт ещё не стартовал или упал | `docker compose ... logs web` — посмотреть стек |
| `Bad Request (400)` на /admin | `ALLOWED_HOSTS` не содержит IP/домен | Добавить в `.env.prod`, `up -d web` |
| `CSRF verification failed` в админке | `CSRF_TRUSTED_ORIGINS` не содержит origin | Добавить полный URL с протоколом |
| Виджет не подключается с внешнего сайта | CORS-блок | `WidgetCORSMiddleware` уже всё разрешает для `/api/widget/*`, проверить response на OPTIONS |
| WebSocket не апгрейдится | `proxy_set_header Upgrade` отсутствует в nginx | Проверить блок `location /ws/` |
| Контейнер `web` крашится с `OperationalError` | БД ещё не готова | Healthcheck должен ждать, но при первом старте может быть 20–30 с — перезапустить `up -d web` |
| Письма не отправляются | Неверный SMTP-пароль | mail.ru требует **пароль приложения**, не основной пароль ящика |
| Долгий билд фронта | Это норма (Next.js standalone собирает ~5 мин на 2 vCPU) | Подождать или взять более мощный тариф |

---

## Чек-лист сдачи

- [ ] Сервер создан, выбран образ с Docker, root-доступ есть
- [ ] Подключился по SSH (с ключом или паролем)
- [ ] `ufw` настроен, открыты только 22 и 80
- [ ] Сменён root-пароль (если входили по паролю)
- [ ] Проект залит в `/opt/multichat`
- [ ] `deploy/.env.prod` заполнен реальными секретами
- [ ] `docker compose ... ps` — все сервисы Up
- [ ] `http://IP/` открывает страницу входа
- [ ] `http://IP/admin/` пускает (после поднятия прав)
- [ ] Дефолтный пароль `admin@admin.com / admin` сменён на сильный
- [ ] Виджет встроен в тестовый HTML и работает
- [ ] WebSocket-уведомления приходят в реальном времени
- [ ] Сделан снапшот Timeweb + ручной `pg_dump`
- [ ] Cron-задача для авто-бэкапа БД настроена

---

## Стоимость за месяц для диплома

| Позиция | Стоимость |
|---|---|
| Cloud Server 2×4 | ~490 ₽ |
| Снапшоты | бесплатно |
| Ежедневный авто-бэкап (опц.) | ~100 ₽ |
| Домен `.ru` на 1 год | ~199 ₽ (≈17 ₽/мес) |
| **Итого без домена** | **~490 ₽/мес** |
| **Итого с авто-бэкапом и доменом** | **~607 ₽/мес** |
