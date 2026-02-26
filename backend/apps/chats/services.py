"""
Сервисный слой для отправки WebSocket-уведомлений из REST views.
"""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def get_layer():
    return get_channel_layer()


def notify_new_chat(chat):
    """Оповещает всех менеджеров о новой заявке (broadcast)."""
    layer = get_layer()
    if not layer:
        return
    async_to_sync(layer.group_send)(
        'notifications_broadcast',
        {
            'type': 'new_chat',
            'chat': {
                'id': chat.id,
                'client_name': chat.client_name,
                'site_id': chat.site_id,
                'channel': chat.channel,
                'status': chat.status,
                'created_at': chat.created_at.isoformat(),
            },
        },
    )


def notify_new_message(message):
    """Отправляет сообщение в WebSocket-группу чата + уведомление менеджеру."""
    layer = get_layer()
    if not layer:
        return

    msg_data = {
        'id': message.id,
        'sender_type': message.sender_type,
        'sender_id': message.sender_id,
        'sender_name': message.sender.first_name if message.sender else None,
        'content': message.content,
        'timestamp': message.timestamp.isoformat(),
        'files': [
            {
                'id': f.id,
                'url': f.file.url,
                'filename': f.filename,
                'mime_type': f.mime_type,
                'file_size': f.file_size,
            }
            for f in message.files.all()
        ],
    }

    # В группу чата
    async_to_sync(layer.group_send)(
        f'chat_{message.chat_id}',
        {
            'type': 'chat_message',
            'message': msg_data,
        },
    )

    # Уведомление назначенному менеджеру
    chat = message.chat
    if chat.assigned_manager_id:
        async_to_sync(layer.group_send)(
            f'notifications_{chat.assigned_manager_id}',
            {
                'type': 'new_message',
                'chat_id': chat.id,
                'message': msg_data,
            },
        )


def notify_chat_status_changed(chat):
    """Уведомляет WebSocket-группу чата об изменении статуса."""
    layer = get_layer()
    if not layer:
        return
    async_to_sync(layer.group_send)(
        f'chat_{chat.id}',
        {
            'type': 'status_changed',
            'chat_id': chat.id,
            'status': chat.status,
        },
    )


def notify_chat_assigned(chat):
    """Уведомляет менеджера о назначении заявки."""
    layer = get_layer()
    if not layer or not chat.assigned_manager_id:
        return
    async_to_sync(layer.group_send)(
        f'notifications_{chat.assigned_manager_id}',
        {
            'type': 'chat_assigned',
            'chat_id': chat.id,
            'manager_id': chat.assigned_manager_id,
        },
    )
