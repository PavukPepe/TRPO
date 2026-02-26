#!/bin/bash
# Скрипт подготовки демо-сайта для тестирования MultiChat Widget
# Использование: ./setup.sh

set -e

API_BASE="http://localhost:8000"
DEMO_EMAIL="admin@demo.com"
DEMO_PASSWORD="demo12345"

echo "=============================="
echo " MultiChat Hub — Demo Setup"
echo "=============================="
echo ""

# 1. Проверяем что backend запущен
echo "[1/5] Проверяю backend..."
if ! curl -s "$API_BASE/api/docs/" > /dev/null 2>&1; then
  echo "❌ Backend не запущен! Запустите:"
  echo "   cd backend && docker compose up -d"
  exit 1
fi
echo "✅ Backend доступен"
echo ""

# 2. Регистрируем тестового пользователя
echo "[2/5] Создаю тестового пользователя ($DEMO_EMAIL)..."
REGISTER_RESP=$(curl -s -X POST "$API_BASE/api/auth/register/" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$DEMO_EMAIL\", \"password\": \"$DEMO_PASSWORD\", \"first_name\": \"Demo Admin\", \"organization_name\": \"TechStore Demo\"}" 2>&1)
echo "    $REGISTER_RESP"
echo ""

# 3. Логинимся
echo "[3/5] Авторизация..."
LOGIN_RESP=$(curl -s -X POST "$API_BASE/api/auth/login/" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$DEMO_EMAIL\", \"password\": \"$DEMO_PASSWORD\"}")
ACCESS_TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access',''))" 2>/dev/null || echo "")

if [ -z "$ACCESS_TOKEN" ]; then
  echo "❌ Не удалось авторизоваться"
  echo "   Ответ: $LOGIN_RESP"
  exit 1
fi
echo "✅ Авторизация успешна"
echo ""

# 4. Создаём тестовый сайт
echo "[4/5] Создаю тестовый сайт..."
SITE_RESP=$(curl -s -X POST "$API_BASE/api/sites/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "name": "TechStore Demo",
    "url": "http://localhost:3001",
    "widget_settings": {
      "desktop": {
        "primaryColor": "#3b82f6",
        "textColor": "#ffffff",
        "welcomeMessage": "Здравствуйте! Добро пожаловать в TechStore. Чем можем помочь?",
        "buttonText": "Чат",
        "position": "right",
        "offsetX": 24,
        "offsetY": 24,
        "autoOpen": true,
        "autoOpenDelay": 10,
        "soundEnabled": true
      },
      "mobile": {
        "show": true,
        "position": "right",
        "offsetX": 16,
        "offsetY": 16,
        "buttonSize": "medium",
        "fullscreenChat": true
      },
      "requireTelegram": false
    },
    "working_hours": {
      "start": "09:00",
      "end": "22:00",
      "timezone": "Europe/Moscow"
    },
    "auto_reply_enabled": true,
    "auto_reply_message": "Спасибо за обращение! Менеджер ответит в ближайшее время."
  }')

SITE_UUID=$(echo "$SITE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('site_uuid',''))" 2>/dev/null || echo "")

if [ -z "$SITE_UUID" ]; then
  echo "❌ Не удалось создать сайт"
  echo "   Ответ: $SITE_RESP"
  exit 1
fi
echo "✅ Сайт создан, UUID: $SITE_UUID"
echo ""

# 5. Подставляем UUID в демо-сайт
echo "[5/5] Обновляю демо-сайт..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
sed -i.bak "s/YOUR-SITE-UUID/$SITE_UUID/g" "$SCRIPT_DIR/index.html"
rm -f "$SCRIPT_DIR/index.html.bak"
echo "✅ UUID подставлен в index.html"
echo ""

echo "=============================="
echo " Готово!"
echo "=============================="
echo ""
echo "📋 Данные для входа в панель управления:"
echo "   URL:    http://localhost:3000/login"
echo "   Email:  $DEMO_EMAIL"
echo "   Пароль: $DEMO_PASSWORD"
echo ""
echo "🌐 Демо-сайт:"
echo "   Откройте index.html в браузере или запустите:"
echo "   python3 -m http.server 3001 --directory $SCRIPT_DIR"
echo "   Затем откройте: http://localhost:3001"
echo ""
echo "💬 Виджет должен появиться в правом нижнем углу демо-сайта"
echo "   Site UUID: $SITE_UUID"
echo ""
