#!/usr/bin/env bash
# =====================================================================
# MultiChat Hub — bootstrap.sh
# Разворачивает весь стек на чистом Ubuntu/Debian VDS одной командой.
#
# Использование:
#   bash deploy/bootstrap.sh
#
# С SMTP-кредами (для рассылки приглашений / восстановления пароля):
#   EMAIL_HOST_USER='you@mail.ru' \
#   EMAIL_HOST_PASSWORD='application-password' \
#   bash deploy/bootstrap.sh
#
# Скрипт идемпотентный: повторный запуск не сломает уже работающий стек.
# =====================================================================
set -euo pipefail

# ---------- настройки --------------------------------------------------
FRONTEND_REPO="${FRONTEND_REPO:-https://github.com/PavukPepe/gitact.git}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/saa-s-dashboard-development"
ENV_FILE="$PROJECT_ROOT/deploy/.env.prod"
COMPOSE="docker compose -f $PROJECT_ROOT/deploy/docker-compose.prod.yml --env-file $ENV_FILE"

# ---------- цвета ------------------------------------------------------
GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RED=$'\e[31m'; BOLD=$'\e[1m'; RST=$'\e[0m'
say()  { printf "%s\n" "${GREEN}▶ $*${RST}"; }
warn() { printf "%s\n" "${YELLOW}⚠ $*${RST}"; }
die()  { printf "%s\n" "${RED}✖ $*${RST}" >&2; exit 1; }

# ---------- проверки ---------------------------------------------------
[[ "$EUID" -eq 0 ]] || die "Запускать от root (sudo bash deploy/bootstrap.sh)"

. /etc/os-release 2>/dev/null || die "Не Linux?"
case "$ID" in
  ubuntu|debian) ;;
  *) warn "ОС $ID — гайд проверялся на Ubuntu/Debian, поехали аккуратно" ;;
esac

# ---------- 1. APT base ------------------------------------------------
say "Обновляю apt и ставлю утилиты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl ca-certificates ufw cron python3 >/dev/null

# ---------- 2. Docker --------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    say "Ставлю Docker (get.docker.com)"
    curl -fsSL https://get.docker.com | sh >/dev/null
    systemctl enable --now docker
else
    say "Docker уже установлен ($(docker --version | awk '{print $3}' | tr -d ','))"
fi

if ! docker compose version >/dev/null 2>&1; then
    say "Ставлю docker-compose-plugin"
    apt-get install -y -qq docker-compose-plugin >/dev/null
fi

# ---------- 3. Фронт-репо ---------------------------------------------
if [[ ! -d "$FRONTEND_DIR/.git" ]]; then
    say "Клонирую фронт из $FRONTEND_REPO"
    rm -rf "$FRONTEND_DIR"
    git clone --depth 1 "$FRONTEND_REPO" "$FRONTEND_DIR"
else
    say "Фронт уже клонирован, обновляю"
    (cd "$FRONTEND_DIR" && git pull --ff-only || warn "git pull в $FRONTEND_DIR не прошёл, продолжаю с тем что есть")
fi

# ---------- 4. .env.prod ----------------------------------------------
SERVER_IP="${SERVER_IP:-$(curl -fsS https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')}"
say "Серверный IP: ${BOLD}$SERVER_IP${RST}"

if [[ ! -f "$ENV_FILE" ]]; then
    say "Генерирую секреты и создаю $ENV_FILE"
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
    DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

    EMAIL_HOST_USER="${EMAIL_HOST_USER:-}"
    EMAIL_HOST_PASSWORD="${EMAIL_HOST_PASSWORD:-}"
    DEFAULT_FROM_EMAIL="${DEFAULT_FROM_EMAIL:-$EMAIL_HOST_USER}"

    cat > "$ENV_FILE" <<EOF
# Сгенерировано bootstrap.sh $(date -Iseconds)
DEBUG=0
SECRET_KEY=$SECRET_KEY
ALLOWED_HOSTS=$SERVER_IP,localhost
CSRF_TRUSTED_ORIGINS=http://$SERVER_IP
CORS_ALLOWED_ORIGINS=http://$SERVER_IP
FRONTEND_URL=http://$SERVER_IP

DB_NAME=multichat
DB_USER=multichat_user
DB_PASSWORD=$DB_PASSWORD
DB_HOST=db
DB_PORT=5432

REDIS_URL=redis://redis:6379/0

EMAIL_HOST=smtp.mail.ru
EMAIL_PORT=465
EMAIL_USE_SSL=1
EMAIL_USE_TLS=0
EMAIL_HOST_USER=$EMAIL_HOST_USER
EMAIL_HOST_PASSWORD=$EMAIL_HOST_PASSWORD
DEFAULT_FROM_EMAIL=$DEFAULT_FROM_EMAIL

INVITE_TOKEN_EXPIRE_HOURS=48
RESET_TOKEN_EXPIRE_HOURS=1

NEXT_PUBLIC_API_URL=
EOF
    chmod 600 "$ENV_FILE"

    if [[ -z "$EMAIL_HOST_USER" ]]; then
        warn "SMTP не заполнен — приглашения и восстановление пароля работать не будут."
        warn "Чтобы добавить позже: nano $ENV_FILE  →  заполни EMAIL_HOST_* + перезапусти web"
    fi
else
    say "$ENV_FILE уже существует — оставляю как есть"
fi

# ---------- 5. Firewall ------------------------------------------------
say "Настраиваю ufw (порты 22, 80)"
ufw allow OpenSSH >/dev/null 2>&1 || true
ufw allow 80/tcp  >/dev/null 2>&1 || true
yes | ufw enable  >/dev/null 2>&1 || true
ufw status verbose | head -15

# ---------- 6. Build & up ----------------------------------------------
say "Собираю Docker-образы (первый раз: 5–10 минут)"
cd "$PROJECT_ROOT"
$COMPOSE build

say "Запускаю стек"
$COMPOSE up -d

# ---------- 7. Ждём бэкенд --------------------------------------------
say "Жду готовности бэкенда (миграции, collectstatic, healthchecks)"
for i in $(seq 1 60); do
    if $COMPOSE exec -T web curl -fsS http://localhost:8000/admin/login/ >/dev/null 2>&1; then
        say "Бэкенд отвечает"
        break
    fi
    sleep 5
    if (( i == 60 )); then
        warn "Бэкенд не поднялся за 5 минут — смотри логи: $COMPOSE logs web"
    fi
done

# ---------- 8. Admin user ---------------------------------------------
say "Поднимаю права администратора Django"
$COMPOSE exec -T web python manage.py shell <<'PY' || warn "Не удалось обновить администратора (возможно, контейнер ещё не готов)"
from django.contrib.auth import get_user_model
U = get_user_model()
email = 'admin@admin.com'
try:
    u = U.objects.get(email=email)
except U.DoesNotExist:
    u = U.objects.create_user(email=email, password='admin', first_name='Admin', role='admin')
u.is_staff = True
u.is_superuser = True
u.set_password('admin')
u.save()
print(f'Admin ready: {email} / admin')
PY

# ---------- 9. Cron бэкапа --------------------------------------------
say "Настраиваю cron на ежедневный pg_dump в 04:00"
mkdir -p "$PROJECT_ROOT/backups"
CRON_TAG="# multichat-daily-backup"
CRON_CMD="0 4 * * * cd $PROJECT_ROOT && docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod exec -T db pg_dump -U multichat_user multichat > $PROJECT_ROOT/backups/db_\$(date +\\%F).sql 2>&1 $CRON_TAG"
( crontab -l 2>/dev/null | grep -v -F "$CRON_TAG" || true; echo "$CRON_CMD" ) | crontab -

# ---------- 10. Сводка ------------------------------------------------
NL=$'\n'
cat <<EOF

${BOLD}════════════════════════════════════════════════════════════════════
                       DEPLOY ЗАВЕРШЁН
════════════════════════════════════════════════════════════════════${RST}

  Фронт:        ${BOLD}http://$SERVER_IP/${RST}
  Django admin: ${BOLD}http://$SERVER_IP/admin/${RST}    (admin@admin.com / admin)
  Swagger API:  http://$SERVER_IP/api/schema/swagger/

  Файл с секретами: $ENV_FILE   ${YELLOW}(права 600, не коммитим)${RST}

  Полезные команды:
    Логи всех сервисов:  docker compose -f deploy/docker-compose.prod.yml logs -f
    Логи одного:         docker compose -f deploy/docker-compose.prod.yml logs -f web
    Рестарт после правок: bash deploy/bootstrap.sh
    Остановить:          docker compose -f deploy/docker-compose.prod.yml down
    Полный сброс (с БД!): docker compose -f deploy/docker-compose.prod.yml down -v

  ${YELLOW}TODO вручную:${RST}
    1. Сменить root-пароль:  passwd
    2. Сменить пароль admin@admin.com через интерфейс (сейчас admin/admin)
    3. Если нужны рассылки — впишите SMTP в $ENV_FILE и:
         $COMPOSE up -d --build web

════════════════════════════════════════════════════════════════════
EOF
