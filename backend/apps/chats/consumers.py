import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import Chat, Message


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket для real-time обмена сообщениями в чате.
    Подключение: ws://host/ws/chat/{chat_id}/?token=<jwt_access_token>

    Отправка сообщения клиентом:
        { "type": "chat.message", "content": "Текст сообщения" }

    Индикатор «печатает»:
        { "type": "typing", "is_typing": true }

    Получаемые события:
        { "type": "chat.message", "message": {...} }
        { "type": "typing", "user_id": 1, "is_typing": true }
        { "type": "status_changed", "chat_id": 1, "status": "in_progress" }
    """

    async def connect(self):
        self.chat_id = self.scope['url_route']['kwargs']['chat_id']
        self.room_group = f'chat_{self.chat_id}'
        user = self.scope.get('user')

        if not user or user.is_anonymous:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group'):
            await self.channel_layer.group_discard(self.room_group, self.channel_name)

    async def receive_json(self, content):
        msg_type = content.get('type', '')
        user = self.scope['user']

        if msg_type == 'chat.message':
            text = content.get('content', '').strip()
            if not text:
                return

            message_data = await self.save_message(user, text)

            await self.channel_layer.group_send(
                self.room_group,
                {
                    'type': 'chat_message',
                    'message': message_data,
                },
            )

        elif msg_type == 'typing':
            await self.channel_layer.group_send(
                self.room_group,
                {
                    'type': 'typing_indicator',
                    'user_id': user.id,
                    'is_typing': content.get('is_typing', False),
                },
            )

    async def chat_message(self, event):
        await self.send_json({
            'type': 'chat.message',
            'message': event['message'],
        })

    async def typing_indicator(self, event):
        await self.send_json({
            'type': 'typing',
            'user_id': event['user_id'],
            'is_typing': event['is_typing'],
        })

    async def status_changed(self, event):
        await self.send_json({
            'type': 'status_changed',
            'chat_id': event['chat_id'],
            'status': event['status'],
        })

    @database_sync_to_async
    def save_message(self, user, content):
        chat = Chat.objects.get(pk=self.chat_id)
        sender_type = Message.SenderType.MANAGER if user.role in ('admin', 'rop', 'manager') else Message.SenderType.CLIENT
        msg = Message.objects.create(
            chat=chat,
            sender_type=sender_type,
            sender=user,
            content=content,
        )
        chat.save()  # обновляет updated_at
        return {
            'id': msg.id,
            'sender_type': msg.sender_type,
            'sender_id': user.id,
            'sender_name': user.first_name,
            'content': msg.content,
            'timestamp': msg.timestamp.isoformat(),
        }


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket для уведомлений менеджера в реальном времени.
    Подключение: ws://host/ws/notifications/?token=<jwt_access_token>

    Получаемые события:
        { "type": "new_chat", "chat": {...} }
        { "type": "chat_assigned", "chat_id": 1, "manager_id": 2 }
        { "type": "new_message", "chat_id": 1, "message": {...} }
        { "type": "chat_reassigned", "chat_id": 1, "reason": "timeout" }
    """

    async def connect(self):
        user = self.scope.get('user')
        if not user or user.is_anonymous:
            await self.close()
            return

        self.user_group = f'notifications_{user.id}'
        # Общая группа для всех менеджеров (для новых заявок)
        self.broadcast_group = 'notifications_broadcast'

        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.channel_layer.group_add(self.broadcast_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        if hasattr(self, 'broadcast_group'):
            await self.channel_layer.group_discard(self.broadcast_group, self.channel_name)

    async def receive_json(self, content):
        # Клиент не шлёт команды в notification-канал
        pass

    # Обработчики событий от channel layer

    async def new_chat(self, event):
        await self.send_json({
            'type': 'new_chat',
            'chat': event['chat'],
        })

    async def chat_assigned(self, event):
        await self.send_json({
            'type': 'chat_assigned',
            'chat_id': event['chat_id'],
            'manager_id': event['manager_id'],
        })

    async def new_message(self, event):
        await self.send_json({
            'type': 'new_message',
            'chat_id': event['chat_id'],
            'message': event['message'],
        })

    async def chat_reassigned(self, event):
        await self.send_json({
            'type': 'chat_reassigned',
            'chat_id': event['chat_id'],
            'from_manager': event.get('from_manager'),
            'to_manager': event.get('to_manager'),
            'reason': event.get('reason', 'timeout'),
        })
