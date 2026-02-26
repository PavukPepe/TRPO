from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.conf import settings
from django.utils import timezone

from datetime import timedelta


@shared_task
def check_chat_response_timeout(chat_id):
    """
    Проверяет, ответил ли менеджер на заявку в отведённое время.
    Если нет — переназначает следующему в очереди и уведомляет РОПа.
    """
    from .models import Chat, ManagerQueue, ManagerStatus, Message

    try:
        chat = Chat.objects.get(pk=chat_id)
    except Chat.DoesNotExist:
        return

    # Если заявка уже закрыта или нет назначенного менеджера — выходим
    if chat.status == Chat.Status.CLOSED or not chat.assigned_manager:
        return

    # Проверяем, есть ли ответ менеджера после назначения
    has_manager_reply = Message.objects.filter(
        chat=chat,
        sender_type=Message.SenderType.MANAGER,
        timestamp__gte=chat.updated_at - timedelta(seconds=10),
    ).exists()

    if has_manager_reply:
        return

    # Менеджер не ответил — переназначаем
    old_manager = chat.assigned_manager
    next_manager = _get_next_manager(old_manager)

    channel_layer = get_channel_layer()

    if next_manager:
        chat.assigned_manager = next_manager
        chat.save()

        # Уведомляем нового менеджера
        async_to_sync(channel_layer.group_send)(
            f'notifications_{next_manager.id}',
            {
                'type': 'chat_reassigned',
                'chat_id': chat.id,
                'from_manager': old_manager.id,
                'to_manager': next_manager.id,
                'reason': 'timeout',
            },
        )

        # Определяем таймаут для нового менеджера
        try:
            status_obj = next_manager.manager_status
            is_online = status_obj.status == ManagerStatus.Status.ONLINE
        except ManagerStatus.DoesNotExist:
            is_online = False

        timeout = (
            settings.CHAT_ASSIGN_ONLINE_TIMEOUT
            if is_online
            else settings.CHAT_ASSIGN_OFFLINE_TIMEOUT
        )
        check_chat_response_timeout.apply_async(
            args=[chat_id],
            countdown=timeout,
        )

    # Уведомляем РОПов
    _notify_rops_about_timeout(chat, old_manager, channel_layer)


@shared_task
def assign_chat_to_next_manager(chat_id):
    """
    Автоматически назначает новую заявку первому доступному менеджеру в очереди.
    """
    from .models import Chat, ManagerQueue, ManagerStatus

    try:
        chat = Chat.objects.get(pk=chat_id)
    except Chat.DoesNotExist:
        return

    if chat.assigned_manager is not None:
        return

    # Определяем организацию по сайту чата
    org_name = chat.site.owner.organization_name

    # Ищем первого активного менеджера в очереди только своей организации
    queue_filter = {'is_active': True}
    if org_name:
        queue_filter['owner__organization_name'] = org_name
    else:
        queue_filter['owner'] = chat.site.owner

    queue_entries = ManagerQueue.objects.filter(
        **queue_filter
    ).select_related('manager').order_by('position')

    channel_layer = get_channel_layer()

    for entry in queue_entries:
        manager = entry.manager
        if not manager.is_active:
            continue

        # Проверяем статус
        try:
            status_obj = manager.manager_status
            if status_obj.status == ManagerStatus.Status.AWAY:
                continue  # Пропускаем «Отошёл»
        except ManagerStatus.DoesNotExist:
            pass

        # Назначаем
        chat.assigned_manager = manager
        chat.status = Chat.Status.IN_PROGRESS
        chat.save()

        # Уведомляем менеджера
        async_to_sync(channel_layer.group_send)(
            f'notifications_{manager.id}',
            {
                'type': 'chat_assigned',
                'chat_id': chat.id,
                'manager_id': manager.id,
            },
        )

        # Определяем таймаут
        try:
            is_online = manager.manager_status.status == ManagerStatus.Status.ONLINE
        except ManagerStatus.DoesNotExist:
            is_online = False

        timeout = (
            settings.CHAT_ASSIGN_ONLINE_TIMEOUT
            if is_online
            else settings.CHAT_ASSIGN_OFFLINE_TIMEOUT
        )
        check_chat_response_timeout.apply_async(
            args=[chat_id],
            countdown=timeout,
        )
        return

    # Если никого не нашли — заявка остаётся в «Новые»


@shared_task
def update_manager_statuses():
    """
    Периодически проверяет активность менеджеров и переводит в оффлайн
    тех, кто не проявлял активности дольше порога.
    Запускается через Celery Beat.
    """
    from apps.users.models import User
    from .models import ManagerStatus

    threshold = timezone.now() - timedelta(seconds=settings.MANAGER_OFFLINE_THRESHOLD)
    managers = User.objects.filter(role__in=['manager', 'rop'], is_active=True)

    for manager in managers:
        status_obj, created = ManagerStatus.objects.get_or_create(
            manager=manager,
            defaults={'status': ManagerStatus.Status.OFFLINE},
        )
        if not created and status_obj.status == ManagerStatus.Status.ONLINE:
            if status_obj.changed_at < threshold:
                status_obj.status = ManagerStatus.Status.OFFLINE
                status_obj.save()


def _get_next_manager(current_manager):
    """Находит следующего менеджера в очереди после текущего."""
    from .models import ManagerQueue, ManagerStatus

    org_name = current_manager.organization_name
    queue_qs = ManagerQueue.objects.filter(is_active=True).select_related('manager')
    if org_name:
        queue_qs = queue_qs.filter(owner__organization_name=org_name)
    else:
        queue_qs = queue_qs.filter(owner=current_manager)

    queue = list(queue_qs.order_by('position'))

    if not queue:
        return None

    # Находим позицию текущего менеджера
    current_idx = None
    for i, entry in enumerate(queue):
        if entry.manager_id == current_manager.id:
            current_idx = i
            break

    if current_idx is None:
        start = 0
    else:
        start = current_idx + 1

    # Обходим по кругу
    for i in range(len(queue)):
        entry = queue[(start + i) % len(queue)]
        manager = entry.manager

        if not manager.is_active or manager.id == current_manager.id:
            continue

        try:
            if manager.manager_status.status == ManagerStatus.Status.AWAY:
                continue
        except ManagerStatus.DoesNotExist:
            pass

        return manager

    return None


def _notify_rops_about_timeout(chat, old_manager, channel_layer):
    """Уведомляет РОПов организации о том, что менеджер не ответил вовремя."""
    from apps.users.models import User

    org_name = chat.site.owner.organization_name
    rops_qs = User.objects.filter(role__in=['rop', 'admin'], is_active=True)
    if org_name:
        rops_qs = rops_qs.filter(organization_name=org_name)
    else:
        rops_qs = rops_qs.filter(pk=chat.site.owner_id)
    rops = rops_qs
    for rop in rops:
        async_to_sync(channel_layer.group_send)(
            f'notifications_{rop.id}',
            {
                'type': 'chat_reassigned',
                'chat_id': chat.id,
                'from_manager': old_manager.id,
                'to_manager': chat.assigned_manager_id,
                'reason': 'manager_timeout',
            },
        )
