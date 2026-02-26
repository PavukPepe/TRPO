import json
import logging

import requests
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task
def process_telegram_update(site_id: int, update: dict):
    """Обрабатывает входящий Telegram update в Celery-задаче."""
    from apps.sites.models import Site
    from .bot import process_update

    try:
        site = Site.objects.get(pk=site_id)
    except Site.DoesNotExist:
        logger.error('Site %s not found for telegram update', site_id)
        return

    process_update(site, update)


@shared_task
def send_telegram_reply(chat_id: int, text: str):
    """Отправляет ответ менеджера клиенту в Telegram."""
    from apps.chats.models import Chat

    try:
        chat = Chat.objects.select_related('site').get(pk=chat_id)
    except Chat.DoesNotExist:
        logger.error('Chat %s not found for telegram reply', chat_id)
        return

    if not chat.telegram_chat_id or not chat.site.telegram_bot_token:
        return

    bot_token = chat.site.telegram_bot_token
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    data = {
        'chat_id': chat.telegram_chat_id,
        'text': text,
        'parse_mode': 'HTML',
    }

    try:
        resp = requests.post(url, json=data, timeout=10)
        if not resp.json().get('ok'):
            logger.warning('Telegram sendMessage failed: %s', resp.text)
    except requests.RequestException as e:
        logger.error('Telegram API error: %s', e)


@shared_task
def send_rating_request(chat_id: int):
    """Отправляет запрос оценки клиенту в Telegram при закрытии чата."""
    from apps.chats.models import Chat

    try:
        chat = Chat.objects.select_related('site').get(pk=chat_id)
    except Chat.DoesNotExist:
        return

    if not chat.telegram_chat_id or not chat.site.telegram_bot_token:
        return

    bot_token = chat.site.telegram_bot_token
    keyboard = {
        'inline_keyboard': [
            [
                {'text': f'{i} ⭐', 'callback_data': json.dumps({
                    'action': 'rate', 'chat_id': chat.id, 'rating': i,
                })}
                for i in range(1, 6)
            ]
        ]
    }

    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    data = {
        'chat_id': chat.telegram_chat_id,
        'text': 'Ваш диалог завершён. Пожалуйста, оцените качество обслуживания:',
        'reply_markup': keyboard,
    }

    try:
        requests.post(url, json=data, timeout=10)
    except requests.RequestException as e:
        logger.error('Telegram rating request error: %s', e)


@shared_task
def handle_rating_callback(site_id: int, callback_query: dict):
    """Обрабатывает callback оценки от клиента."""
    from apps.chats.models import Chat, Rating
    from apps.sites.models import Site

    try:
        data = json.loads(callback_query.get('data', '{}'))
    except (json.JSONDecodeError, TypeError):
        return

    if data.get('action') != 'rate':
        return

    chat_id = data.get('chat_id')
    rating_value = data.get('rating')

    if not chat_id or not rating_value:
        return

    try:
        chat = Chat.objects.get(pk=chat_id)
        site = Site.objects.get(pk=site_id)
    except (Chat.DoesNotExist, Site.DoesNotExist):
        return

    # Проверяем, нет ли уже оценки
    if hasattr(chat, 'rating'):
        return

    # Создаём оценку
    if chat.assigned_manager:
        Rating.objects.create(
            chat=chat,
            manager=chat.assigned_manager,
            rating=rating_value,
        )

    # Отвечаем клиенту
    bot_token = site.telegram_bot_token
    if bot_token:
        url = f'https://api.telegram.org/bot{bot_token}/answerCallbackQuery'
        requests.post(url, json={
            'callback_query_id': callback_query['id'],
            'text': f'Спасибо за оценку {rating_value} ⭐!',
        }, timeout=10)

        # Обновляем сообщение
        msg_id = callback_query.get('message', {}).get('message_id')
        if msg_id:
            edit_url = f'https://api.telegram.org/bot{bot_token}/editMessageText'
            requests.post(edit_url, json={
                'chat_id': callback_query['message']['chat']['id'],
                'message_id': msg_id,
                'text': f'Спасибо за оценку {rating_value} ⭐! Всего доброго!',
            }, timeout=10)
