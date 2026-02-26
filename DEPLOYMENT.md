# Инструкция по развёртке MultiChat

## Требования

- Docker Desktop (или Docker Engine + Docker Compose)
- Node.js 18+ и npm (для фронтенда)
- Git

---

## Структура проекта

```
Димплом/
├── backend/          # Django + Channels (API, WebSocket)
└── saa-s-dashboard-development/   # Next.js (Dashboard)
```

---

## 1. Развёртка бэкенда

### 1.1 Перейти в папку бэкенда

```bash
cd backend
```

### 1.2 Создать файл окружения

Скопировать шаблон и задать переменные:

```bash
cp .env.example .env   # или отредактировать существующий .env
```

Минимальное содержание `.env` для продакшена:

```env
DEBUG=0
SECRET_KEY=замените-на-случайную-строку-минимум-50-символов

ALLOWED_HOSTS=ваш-домен.ru,www.ваш-домен.ru

DB_NAME=multichat
DB_USER=multichat_user
DB_PASSWORD=придумайте-сложный-пароль
DB_HOST=db
DB_PORT=5432

REDIS_URL=redis://redis:6379/0

CORS_ALLOWED_ORIGINS=https://ваш-домен.ru
```

> **Для локального запуска** можно оставить `DEBUG=1` и стандартные значения из `.env`.

### 1.3 Запустить контейнеры

```bash
docker compose up -d --build
```

При первом запуске автоматически выполняется:
- Ожидание готовности базы данных
- `migrate` — применение миграций
- `create_default_admin` — создание администратора по умолчанию (только если нет пользователей)
- `collectstatic` — сборка статики

### 1.4 Администратор по умолчанию

При первом запуске создаётся учётная запись:

| Поле | Значение |
|------|----------|
| Email | `admin@admin.com` |
| Пароль | `admin` |

> ⚠️ **Обязательно смените пароль** после первого входа через профиль или через сброс пароля в разделе «Менеджеры».

### 1.5 Проверка

```bash
# Статус контейнеров
docker compose ps

# Логи при запуске
docker compose logs web

# API должен отвечать
curl http://localhost:8000/api/auth/login/
```

---

## 2. Развёртка фронтенда (Dashboard)

### 2.1 Перейти в папку фронтенда

```bash
cd saa-s-dashboard-development
```

### 2.2 Установить зависимости

```bash
npm install
```

### 2.3 Создать файл окружения

```bash
# Создать .env.local
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
```

Для продакшена:
```env
NEXT_PUBLIC_API_URL=https://ваш-домен.ru
```

### 2.4 Запуск в режиме разработки

```bash
npm run dev
```

Dashboard доступен по адресу: [http://localhost:3000](http://localhost:3000)

### 2.5 Сборка для продакшена

```bash
npm run build
npm run start
```

---

## 3. Быстрый старт (всё сразу)

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd Димплом

# 2. Запустить бэкенд
cd backend
docker compose up -d --build

# 3. В новом терминале — запустить фронтенд
cd ../saa-s-dashboard-development
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

Открыть [http://localhost:3000](http://localhost:3000), войти: `admin@admin.com` / `admin`

---

## 4. Обновление (уже развёрнутое приложение)

```bash
cd backend

# Пересобрать образ и перезапустить
docker compose up -d --build

# Миграции применяются автоматически при запуске
```

---

## 5. Полезные команды

```bash
# Просмотр логов в реальном времени
docker compose logs -f web

# Перезапуск только web-сервиса (после изменений Python-кода)
docker compose restart web

# Подключиться к Django shell
docker compose exec web python manage.py shell

# Создать суперпользователя вручную
docker compose exec web python manage.py createsuperuser

# Резервная копия базы данных
docker compose exec db pg_dump -U multichat_user multichat > backup.sql

# Восстановление из резервной копии
docker compose exec -T db psql -U multichat_user multichat < backup.sql
```

---

## 6. Порты по умолчанию

| Сервис | Порт |
|--------|------|
| Backend API | 8000 |
| Frontend Dashboard | 3000 |
| PostgreSQL | 5432 |
| Redis | 6379 |

---

## 7. Встраиваемый виджет

После развёртки бэкенда, на страницу клиентского сайта вставить:

```html
<script src="http://localhost:8000/static/widget/widget.js"
        data-site-id="UUID-САЙТА-ИЗ-НАСТРОЕК"></script>
```

UUID сайта можно скопировать на странице **Сайты** в дашборде.
