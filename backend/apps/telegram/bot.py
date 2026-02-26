"""
Основная логика Telegram-бота.
Обрабатывает входящие update'ы от Telegram: /start, текстовые сообщения, callback_query.
"""
import json
import logging

import requests
from django.conf import settings

from apps.chats.models import Chat, Message
from apps.chats.services import notify_new_chat, notify_new_message
from apps.chats.tasks import assign_chat_to_next_manager
from apps.sites.models import Site

from .models import TelegramUser

logger = logging.getLogger(__name__)


def telegram_api(bot_token: str, method: str, data: dict | None = None) -> dict:
    """Вызов Telegram Bot API."""
    url = f'https://api.telegram.org/bot{bot_token}/{method}'
    resp = requests.post(url, json=data or {}, timeout=10)
    return resp.json()


def send_message(bot_token: str, chat_id: int, text: str, reply_markup: dict | None = None):
    """Отправляет текстовое сообщение в Telegram."""
    data = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if reply_markup:
        data['reply_markup'] = reply_markup
    return telegram_api(bot_token, 'sendMessage', data)


def process_update(site: Site, update: dict):
    """
    Точка входа для обработки Telegram update.
    Определяет тип update и вызывает соответствующий обработчик.
    """
    bot_token = site.telegram_bot_token
    if not bot_token:
        logger.warning('Site %s has no telegram_bot_token', site.id)
        return

    if 'callback_query' in update:
        _handle_callback_query(site, bot_token, update['callback_query'])
    elif 'message' in update:
        message = update['message']
        text = message.get('text', '')

        if text.startswith('/start'):
            _handle_start(site, bot_token, message)
        else:
            _handle_message(site, bot_token, message)


def _get_or_create_tg_user(tg_from: dict) -> TelegramUser:
    """Создаёт или обновляет TelegramUser из данных Telegram."""
    tg_user, created = TelegramUser.objects.update_or_create(
        telegram_id=tg_from['id'],
        defaults={
            'username': tg_from.get('username', ''),
            'first_name': tg_from.get('first_name', ''),
            'last_name': tg_from.get('last_name', ''),
        },
    )
    return tg_user


def _find_active_chat(telegram_chat_id: int, site: Site) -> Chat | None:
    """Ищет активный (не закрытый) чат для данного Telegram-чата."""
    return Chat.objects.filter(
        telegram_chat_id=telegram_chat_id,
        site=site,
    ).exclude(status=Chat.Status.CLOSED).order_by('-updated_at').first()


def _create_chat(site: Site, tg_user: TelegramUser, telegram_chat_id: int) -> Chat:
    """Создаёт новый чат из Telegram."""
    name = tg_user.first_name
    if tg_user.last_name:
        name += f' {tg_user.last_name}'

    chat = Chat.objects.create(
        site=site,
        client_name=name,
        telegram_username=tg_user.username,
        telegram_user_id=tg_user.telegram_id,
        telegram_chat_id=telegram_chat_id,
        channel=Chat.Channel.TELEGRAM,
        status=Chat.Status.NEW,
    )
    notify_new_chat(chat)
    assign_chat_to_next_manager.delay(chat.id)
    return chat


def _save_client_message(chat: Chat, text: str) -> Message:
    """Сохраняет сообщение клиента из Telegram."""
    message = Message.objects.create(
        chat=chat,
        sender_type=Message.SenderType.CLIENT,
        content=text,
    )
    chat.save()  # обновляет updated_at
    notify_new_message(message)
    return message


def _check_auto_reply(site: Site, bot_token: str, telegram_chat_id: int):
    """Отправляет авто-ответ, если включён."""
    if site.auto_reply_enabled and site.auto_reply_message:
        send_message(bot_token, telegram_chat_id, site.auto_reply_message)


def _handle_start(site: Site, bot_token: str, message: dict):
    """
    Обработка /start.
    - /start {referral_code} — привязка к конкретному сайту (сценарий 2)
    - /start без параметров — если бот привязан к одному сайту, создаём чат сразу
    """
    tg_from = message.get('from', {})
    telegram_chat_id = message['chat']['id']
    text = message.get('text', '')

    tg_user = _get_or_create_tg_user(tg_from)

    # Парсим referral_code
    parts = text.split(maxsplit=1)
    referral_code = parts[1].strip() if len(parts) > 1 else None

    if referral_code:
        # Сценарий 2: переход по реферальной ссылке
        try:
            ref_site = Site.objects.get(telegram_referral_code=referral_code)
        except Site.DoesNotExist:
            send_message(bot_token, telegram_chat_id, 'Ссылка недействительна.')
            return

        # Проверяем, нет ли уже активного чата
        existing = _find_active_chat(telegram_chat_id, ref_site)
        if existing:
            send_message(bot_token, telegram_chat_id,
                         'У вас уже есть активный диалог. Просто напишите ваше сообщение.')
            return

        chat = _create_chat(ref_site, tg_user, telegram_chat_id)
        send_message(bot_token, telegram_chat_id,
                     f'Добро пожаловать! Вы обратились в «{ref_site.name}».\n'
                     'Напишите ваш вопрос, и мы ответим в ближайшее время.')
        _check_auto_reply(ref_site, bot_token, telegram_chat_id)
        return

    # Сценарий 3: /start без параметров — бот привязан к текущему сайту
    existing = _find_active_chat(telegram_chat_id, site)
    if existing:
        send_message(bot_token, telegram_chat_id,
                     'У вас уже есть активный диалог. Просто напишите ваше сообщение.')
        return

    # Проверяем, есть ли другие сайты с этим же bot_token (мультисайтовый бот)
    sites_with_token = list(
        Site.objects.filter(telegram_bot_token=bot_token).values_list('id', 'name')
    )

    if len(sites_with_token) > 1:
        # Показываем клавиатуру выбора сайта
        keyboard = {
            'inline_keyboard': [
                [{'text': name, 'callback_data': json.dumps({'action': 'select_site', 'site_id': sid})}]
                for sid, name in sites_with_token
            ]
        }
        send_message(bot_token, telegram_chat_id,
                     'Выберите компанию, в которую хотите обратиться:',
                     reply_markup=keyboard)
    else:
        # Один сайт — создаём чат сразу
        chat = _create_chat(site, tg_user, telegram_chat_id)
        send_message(bot_token, telegram_chat_id,
                     f'Добро пожаловать в «{site.name}»!\n'
                     'Напишите ваш вопрос, и мы ответим в ближайшее время.')
        _check_auto_reply(site, bot_token, telegram_chat_id)


def _handle_callback_query(site: Site, bot_token: str, callback_query: dict):
    """Обработка callback_query — выбор сайта из inline-клавиатуры (сценарий 3)."""
    tg_from = callback_query.get('from', {})
    telegram_chat_id = callback_query['message']['chat']['id']

    try:
        data = json.loads(callback_query.get('data', '{}'))
    except (json.JSONDecodeError, TypeError):
        return

    if data.get('action') != 'select_site':
        return

    site_id = data.get('site_id')
    try:
        selected_site = Site.objects.get(pk=site_id)
    except Site.DoesNotExist:
        return

    tg_user = _get_or_create_tg_user(tg_from)

    existing = _find_active_chat(telegram_chat_id, selected_site)
    if existing:
        send_message(bot_token, telegram_chat_id,
                     'У вас уже есть активный диалог. Просто напишите ваше сообщение.')
        return

    chat = _create_chat(selected_site, tg_user, telegram_chat_id)
    send_message(bot_token, telegram_chat_id,
                 f'Вы обратились в «{selected_site.name}».\n'
                 'Напишите ваш вопрос, и мы ответим в ближайшее время.')
    _check_auto_reply(selected_site, bot_token, telegram_chat_id)

    # Ответ на callback, чтобы убрать «часики»
    telegram_api(bot_token, 'answerCallbackQuery', {
        'callback_query_id': callback_query['id'],
    })


def _handle_message(site: Site, bot_token: str, message: dict):
    """
    Обработка обычного текстового сообщения.
    Ищет активный чат, если нет — создаёт новый.
    """
    tg_from = message.get('from', {})
    telegram_chat_id = message['chat']['id']
    text = message.get('text', '')

    if not text:
        # Пока обрабатываем только текст
        return

    tg_user = _get_or_create_tg_user(tg_from)

    # Ищем активный чат для этого telegram_chat_id и сайта
    chat = _find_active_chat(telegram_chat_id, site)

    if not chat:
        # Проверяем, есть ли несколько сайтов с этим bot_token
        sites_count = Site.objects.filter(telegram_bot_token=bot_token).count()
        if sites_count > 1:
            send_message(bot_token, telegram_chat_id,
                         'Сначала выберите компанию. Отправьте /start для начала.')
            return

        # Один сайт — создаём чат автоматически
        chat = _create_chat(site, tg_user, telegram_chat_id)
        _check_auto_reply(site, bot_token, telegram_chat_id)

    _save_client_message(chat, text)
