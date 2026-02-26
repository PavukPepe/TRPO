import json
import logging

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sites.models import Site

from .tasks import process_telegram_update, handle_rating_callback

logger = logging.getLogger(__name__)


class TelegramWebhookView(APIView):
    """
    Принимает вебхуки от Telegram Bot API.
    URL: POST /api/telegram/webhook/{site_uuid}/
    Без аутентификации — проверяется site_uuid.
    """
    permission_classes = [AllowAny]
    authentication_classes = []  # Отключаем JWT для webhook

    def post(self, request, site_uuid):
        try:
            site = Site.objects.get(site_uuid=site_uuid)
        except Site.DoesNotExist:
            return Response(status=404)

        update = request.data
        if not update:
            return Response(status=400)

        # Проверяем, не является ли это callback с оценкой
        callback = update.get('callback_query')
        if callback:
            try:
                data = json.loads(callback.get('data', '{}'))
                if data.get('action') == 'rate':
                    handle_rating_callback.delay(site.id, callback)
                    return Response(status=200)
            except (json.JSONDecodeError, TypeError):
                pass

        # Обрабатываем в Celery-задаче
        process_telegram_update.delay(site.id, update)
        return Response(status=200)
