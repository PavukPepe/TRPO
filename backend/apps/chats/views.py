from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.permissions import IsAdmin, IsManager, IsROP

from .models import Chat, File, ManagerQueue, ManagerStatus, Message, Rating, Template

ALLOWED_MIME_TYPES = frozenset({
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf',
})
from .serializers import (
    ChatAssignSerializer,
    ChatCreateSerializer,
    ChatDetailSerializer,
    ChatListSerializer,
    ChatMergeSerializer,
    ChatStatusSerializer,
    ManagerQueueSerializer,
    ManagerStatusSerializer,
    MessageCreateSerializer,
    MessageSerializer,
    RatingSerializer,
    TemplateSerializer,
)
from .services import (
    notify_chat_assigned,
    notify_chat_status_changed,
    notify_new_chat,
    notify_new_message,
)
from .tasks import assign_chat_to_next_manager

User = get_user_model()


class ChatViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsManager]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'channel', 'site', 'assigned_manager']
    search_fields = ['client_name', 'telegram_username', 'messages__content']
    ordering_fields = ['created_at', 'updated_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return ChatListSerializer
        if self.action == 'create':
            return ChatCreateSerializer
        return ChatDetailSerializer

    def perform_create(self, serializer):
        chat = serializer.save()
        notify_new_chat(chat)
        assign_chat_to_next_manager.delay(chat.id)

    def get_queryset(self):
        user = self.request.user
        org_name = user.organization_name

        # Базовый фильтр по организации
        if org_name:
            qs = Chat.objects.select_related('site', 'assigned_manager').filter(
                site__owner__organization_name=org_name
            )
        else:
            qs = Chat.objects.select_related('site', 'assigned_manager').filter(
                site__owner=user
            )

        if user.role == 'manager':
            qs = qs.filter(
                Q(assigned_manager=user) |
                Q(status=Chat.Status.NEW) |
                Q(status=Chat.Status.REPLIED)
            )
        return qs

    @action(detail=True, methods=['put'], url_path='assign')
    def assign_manager(self, request, pk=None):
        chat = self.get_object()
        serializer = ChatAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        manager = User.objects.get(pk=serializer.validated_data['manager_id'])
        chat.assigned_manager = manager
        if chat.status == Chat.Status.NEW:
            chat.status = Chat.Status.IN_PROGRESS
        chat.save()
        notify_chat_assigned(chat)
        return Response(ChatDetailSerializer(chat).data)

    @action(detail=True, methods=['put'], url_path='status')
    def change_status(self, request, pk=None):
        chat = self.get_object()
        serializer = ChatStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data['status']
        chat.status = new_status
        if new_status == Chat.Status.CLOSED:
            chat.closed_at = timezone.now()
        chat.save()
        notify_chat_status_changed(chat)

        # Запрос оценки в Telegram при закрытии
        if new_status == Chat.Status.CLOSED and chat.channel == Chat.Channel.TELEGRAM and chat.telegram_chat_id:
            from apps.telegram.tasks import send_rating_request
            send_rating_request.delay(chat.id)

        return Response(ChatDetailSerializer(chat).data)

    @action(detail=True, methods=['post'], url_path='merge')
    def merge(self, request, pk=None):
        chat = self.get_object()
        serializer = ChatMergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = Chat.objects.get(pk=serializer.validated_data['target_chat_id'])

        # Переносим все сообщения из текущего чата в целевой
        Message.objects.filter(chat=chat).update(chat=target)
        chat.delete()

        return Response(ChatDetailSerializer(target).data)


class MessageListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsManager]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return MessageCreateSerializer
        return MessageSerializer

    def get_queryset(self):
        return Message.objects.filter(
            chat_id=self.kwargs['chat_id']
        ).select_related('sender')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        chat = Chat.objects.select_related('site').get(pk=self.kwargs['chat_id'])
        message = serializer.save(
            chat=chat,
            sender_type=Message.SenderType.MANAGER,
            sender=request.user,
        )

        # Автоназначение: если у чата нет ответственного — назначаем ответившего
        auto_assigned = False
        if not chat.assigned_manager_id:
            chat.assigned_manager = request.user
            auto_assigned = True

        # Автостатус: Новый → В обработке при первом ответе менеджера
        if chat.status == Chat.Status.NEW:
            chat.status = Chat.Status.IN_PROGRESS

        chat.save()  # обновляет updated_at (+ авто-изменения)

        if auto_assigned:
            notify_chat_assigned(chat)

        # Сохраняем прикреплённые файлы
        for f in request.FILES.getlist('files'):
            if f.content_type in ALLOWED_MIME_TYPES and f.size <= 10 * 1024 * 1024:
                File.objects.create(
                    message=message,
                    file=f,
                    filename=f.name,
                    file_size=f.size,
                    mime_type=f.content_type,
                )

        notify_new_message(message)

        # Пересылка в Telegram, если чат из Telegram-канала
        if chat.channel == Chat.Channel.TELEGRAM and chat.telegram_chat_id:
            from apps.telegram.tasks import send_telegram_reply
            send_telegram_reply.delay(chat.id, message.content)

        return Response(
            MessageSerializer(message, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class RatingCreateView(generics.CreateAPIView):
    serializer_class = RatingSerializer
    permission_classes = [IsAuthenticated]


class TemplateViewSet(viewsets.ModelViewSet):
    serializer_class = TemplateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Template.objects.filter(Q(user=user) | Q(user__isnull=True))

    def perform_create(self, serializer):
        # Только admin может создавать общие шаблоны (user=NULL)
        if self.request.user.role != 'admin':
            serializer.save(user=self.request.user)
        else:
            serializer.save()


class ManagerQueueView(generics.ListCreateAPIView):
    serializer_class = ManagerQueueSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def _org_queue_qs(self):
        user = self.request.user
        org_name = user.organization_name
        if org_name:
            return ManagerQueue.objects.filter(
                owner__organization_name=org_name
            ).select_related('manager')
        return ManagerQueue.objects.filter(owner=user).select_related('manager')

    def get_queryset(self):
        return self._org_queue_qs()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ManagerQueueUpdateView(generics.UpdateAPIView):
    serializer_class = ManagerQueueSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        user = self.request.user
        org_name = user.organization_name
        if org_name:
            return ManagerQueue.objects.filter(owner__organization_name=org_name)
        return ManagerQueue.objects.filter(owner=user)


class ManagerStatusView(generics.RetrieveUpdateAPIView):
    serializer_class = ManagerStatusSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        obj, _ = ManagerStatus.objects.get_or_create(
            manager=self.request.user,
            defaults={'status': ManagerStatus.Status.ONLINE},
        )
        return obj


class HeartbeatView(generics.GenericAPIView):
    """
    POST /api/chats/heartbeat/
    Обновляет время активности менеджера. Фронт вызывает каждые 2 минуты.
    Автоматически ставит статус online.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ms, _ = ManagerStatus.objects.get_or_create(
            manager=request.user,
            defaults={'status': ManagerStatus.Status.ONLINE},
        )
        if ms.status == ManagerStatus.Status.OFFLINE:
            ms.status = ManagerStatus.Status.ONLINE
        ms.save()  # обновляет changed_at
        return Response({'status': ms.status})
