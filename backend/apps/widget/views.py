from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chats.models import Chat, File, Message
from apps.sites.models import Site
from django.utils import timezone


def _is_outside_working_hours(working_hours: dict) -> bool:
    """
    Возвращает True, если текущее время вне рабочего расписания.
    Формат working_hours: {"start": "09:00", "end": "18:00", "timezone": "Europe/Moscow"}
    Если расписание не задано — возвращает False (всегда рабочее время).
    """
    if not working_hours:
        return False
    start_str = working_hours.get('start', '')
    end_str = working_hours.get('end', '')
    tz_name = working_hours.get('timezone', 'UTC')
    if not start_str or not end_str:
        return False
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        tz = ZoneInfo('UTC')
    try:
        now_local = datetime.now(tz).time()
        sh, sm = map(int, start_str.split(':'))
        eh, em = map(int, end_str.split(':'))
        return now_local < dtime(sh, sm) or now_local >= dtime(eh, em)
    except Exception:
        return False


def _maybe_send_auto_reply(site, chat):
    """
    Отправляет автоответ если: автоответ включён, сообщение задано и сейчас нерабочее время.
    Не спамит: не отправляет повторно если системное сообщение было < 10 минут назад.
    """
    if not site.auto_reply_enabled or not site.auto_reply_message:
        return
    if not _is_outside_working_hours(site.working_hours):
        return
    # Не спамим — ограничение 1 автоответ в 10 минут на чат
    recent = chat.messages.filter(
        sender_type=Message.SenderType.SYSTEM,
        timestamp__gte=timezone.now() - timedelta(minutes=10),
    ).exists()
    if recent:
        return
    Message.objects.create(
        chat=chat,
        sender_type=Message.SenderType.SYSTEM,
        content=site.auto_reply_message,
    )

from .serializers import (
    WidgetChatCreateSerializer,
    WidgetChatSerializer,
    WidgetConfigSerializer,
    WidgetMessageSerializer,
    WidgetSendMessageSerializer,
)

ALLOWED_MIME_TYPES = frozenset({
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf',
})


class WidgetConfigView(APIView):
    """
    GET /api/widget/{site_uuid}/config/
    Возвращает настройки виджета (публичный эндпоинт, без авторизации).
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, site_uuid):
        try:
            site = Site.objects.get(site_uuid=site_uuid)
        except Site.DoesNotExist:
            return Response({'detail': 'Сайт не найден.'}, status=status.HTTP_404_NOT_FOUND)

        data = WidgetConfigSerializer({
            'site_uuid': site.site_uuid,
            'site_name': site.name,
            'widget_settings': site.widget_settings,
            'working_hours': site.working_hours,
            'auto_reply_enabled': site.auto_reply_enabled,
            'auto_reply_message': site.auto_reply_message,
        }).data

        return Response(data)


class WidgetChatView(APIView):
    """
    POST /api/widget/{site_uuid}/chat/
    Создаёт новый чат от клиента виджета.

    GET /api/widget/{site_uuid}/chat/?session_id=xxx
    Возвращает чат по session_id (session_id хранится в localStorage виджета).
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, site_uuid):
        session_id = request.query_params.get('session_id', '')
        if not session_id:
            return Response({'detail': 'session_id обязателен.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            site = Site.objects.get(site_uuid=site_uuid)
        except Site.DoesNotExist:
            return Response({'detail': 'Сайт не найден.'}, status=status.HTTP_404_NOT_FOUND)

        chat = Chat.objects.filter(
            site=site,
            channel=Chat.Channel.WIDGET,
            client_email=session_id,
        ).exclude(status=Chat.Status.CLOSED).order_by('-updated_at').first()

        if not chat:
            return Response({'detail': 'Чат не найден.'}, status=status.HTTP_404_NOT_FOUND)

        return Response(WidgetChatSerializer(chat).data)

    def post(self, request, site_uuid):
        try:
            site = Site.objects.get(site_uuid=site_uuid)
        except Site.DoesNotExist:
            return Response({'detail': 'Сайт не найден.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = WidgetChatCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session_id = request.data.get('session_id', '').strip()
        actual_email = serializer.validated_data.get('client_email', '').strip()

        # 1. Ищем существующий открытый чат по session_id (обратная совместимость)
        existing = None
        if session_id:
            existing = Chat.objects.filter(
                site=site,
                channel=Chat.Channel.WIDGET,
                client_email=session_id,
            ).exclude(status=Chat.Status.CLOSED).order_by('-updated_at').first()

        # 2. Если по session_id не нашли — ищем по реальному email
        if not existing and actual_email:
            existing = Chat.objects.filter(
                site=site,
                channel=Chat.Channel.WIDGET,
                client_email=actual_email,
            ).exclude(status=Chat.Status.CLOSED).order_by('-updated_at').first()

        if existing:
            return Response(WidgetChatSerializer(existing).data, status=status.HTTP_200_OK)

        chat = Chat.objects.create(
            site=site,
            client_name=serializer.validated_data.get('client_name', ''),
            client_email=actual_email or session_id,  # Предпочитаем реальный email
            channel=Chat.Channel.WIDGET,
            status=Chat.Status.NEW,
        )

        initial_message = serializer.validated_data.get('initial_message', '')
        if initial_message:
            Message.objects.create(
                chat=chat,
                sender_type=Message.SenderType.CLIENT,
                content=initial_message,
            )

        # Автоответ — только вне рабочего времени
        _maybe_send_auto_reply(site, chat)

        # Уведомление через WebSocket
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'site_{site.id}',
                {
                    'type': 'new_chat',
                    'chat_id': chat.id,
                    'client_name': chat.client_name,
                    'channel': 'widget',
                },
            )
        except Exception:
            pass

        return Response(WidgetChatSerializer(chat).data, status=status.HTTP_201_CREATED)


class WidgetMessagesView(APIView):
    """
    GET  /api/widget/{site_uuid}/chat/{chat_id}/messages/
    POST /api/widget/{site_uuid}/chat/{chat_id}/messages/
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def _get_chat(self, site_uuid, chat_id):
        try:
            site = Site.objects.get(site_uuid=site_uuid)
        except Site.DoesNotExist:
            return None, Response({'detail': 'Сайт не найден.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            chat = Chat.objects.get(id=chat_id, site=site, channel=Chat.Channel.WIDGET)
        except Chat.DoesNotExist:
            return None, Response({'detail': 'Чат не найден.'}, status=status.HTTP_404_NOT_FOUND)

        return chat, None

    def get(self, request, site_uuid, chat_id):
        chat, error = self._get_chat(site_uuid, chat_id)
        if error:
            return error

        # Поддерживаем long-polling: after_id для получения только новых сообщений
        after_id = request.query_params.get('after_id')
        messages = chat.messages.all()
        if after_id:
            messages = messages.filter(id__gt=int(after_id))

        return Response(WidgetMessageSerializer(messages, many=True, context={'request': request}).data)

    def post(self, request, site_uuid, chat_id):
        chat, error = self._get_chat(site_uuid, chat_id)
        if error:
            return error

        if chat.status == Chat.Status.CLOSED:
            return Response({'detail': 'Чат закрыт.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = WidgetSendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content = serializer.validated_data.get('content', '').strip()
        has_files = bool(request.FILES.getlist('files'))

        if not content and not has_files:
            return Response({'detail': 'Нужен текст или файл.'}, status=status.HTTP_400_BAD_REQUEST)

        message = Message.objects.create(
            chat=chat,
            sender_type=Message.SenderType.CLIENT,
            content=content,
        )

        # Сохраняем прикреплённые файлы
        saved_files = []
        for f in request.FILES.getlist('files'):
            if f.content_type in ALLOWED_MIME_TYPES and f.size <= 10 * 1024 * 1024:
                file_obj = File.objects.create(
                    message=message,
                    file=f,
                    filename=f.name,
                    file_size=f.size,
                    mime_type=f.content_type,
                )
                saved_files.append({
                    'id': file_obj.id,
                    'url': request.build_absolute_uri(file_obj.file.url),
                    'filename': file_obj.filename,
                    'mime_type': file_obj.mime_type,
                })

        # Автоответ — только вне рабочего времени
        _maybe_send_auto_reply(chat.site, chat)

        # Обновляем статус чата
        if chat.status == Chat.Status.REPLIED:
            chat.status = Chat.Status.IN_PROGRESS
            chat.save(update_fields=['status', 'updated_at'])

        # WebSocket уведомление менеджеру
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'chat_{chat.id}',
                {
                    'type': 'chat_message',
                    'message': {
                        'id': message.id,
                        'sender_type': 'client',
                        'content': message.content,
                        'timestamp': message.timestamp.isoformat(),
                        'files': saved_files,
                    },
                },
            )
        except Exception:
            pass

        return Response(
            WidgetMessageSerializer(message, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )
