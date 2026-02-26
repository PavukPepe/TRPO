import requests as http_requests

from django.conf import settings
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.permissions import IsAdmin

from .models import Site
from .serializers import SiteSerializer


class SiteViewSet(viewsets.ModelViewSet):
    serializer_class = SiteSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        org_name = self.request.user.organization_name
        if org_name:
            return Site.objects.filter(owner__organization_name=org_name)
        return Site.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['get'], url_path='widget-code')
    def widget_code(self, request, pk=None):
        site = self.get_object()
        api_base = request.build_absolute_uri('/').rstrip('/')
        code = (
            f'<script src="{api_base}/static/widget/widget.js" '
            f'data-site-id="{site.site_uuid}"></script>'
        )
        return Response({'embed_code': code})

    @action(detail=True, methods=['post'], url_path='setup-telegram')
    def setup_telegram(self, request, pk=None):
        """
        Регистрирует webhook в Telegram Bot API для данного сайта.
        Генерирует URL вида: {TELEGRAM_WEBHOOK_BASE_URL}/api/telegram/webhook/{site_uuid}/
        """
        site = self.get_object()
        if not site.telegram_bot_token:
            return Response(
                {'detail': 'Сначала укажите telegram_bot_token для сайта.'},
                status=400,
            )

        base_url = getattr(settings, 'TELEGRAM_WEBHOOK_BASE_URL', '')
        if not base_url:
            return Response(
                {'detail': 'TELEGRAM_WEBHOOK_BASE_URL не настроен на сервере.'},
                status=400,
            )

        webhook_url = f'{base_url}/api/telegram/webhook/{site.site_uuid}/'

        # Регистрируем webhook в Telegram
        tg_url = f'https://api.telegram.org/bot{site.telegram_bot_token}/setWebhook'
        try:
            resp = http_requests.post(tg_url, json={'url': webhook_url}, timeout=10)
            result = resp.json()
        except http_requests.RequestException as e:
            return Response({'detail': f'Ошибка при обращении к Telegram API: {e}'}, status=502)

        if not result.get('ok'):
            return Response(
                {'detail': f'Telegram API вернул ошибку: {result.get("description", "Unknown")}'},
                status=400,
            )

        # Получаем info о боте для отображения ссылки
        bot_info_url = f'https://api.telegram.org/bot{site.telegram_bot_token}/getMe'
        bot_username = ''
        try:
            bot_resp = http_requests.get(bot_info_url, timeout=10).json()
            if bot_resp.get('ok'):
                bot_username = bot_resp['result'].get('username', '')
        except http_requests.RequestException:
            pass

        referral_link = ''
        if bot_username and site.telegram_referral_code:
            referral_link = f'https://t.me/{bot_username}?start={site.telegram_referral_code}'

        return Response({
            'ok': True,
            'webhook_url': webhook_url,
            'bot_username': bot_username,
            'referral_link': referral_link,
        })
