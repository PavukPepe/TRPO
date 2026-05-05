import email as email_lib
import imaplib
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import decode_header
from email.utils import parseaddr, make_msgid

from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.conf import settings
from django.utils import timezone

from datetime import timedelta


def _decode_header_value(value):
    """Декодирует заголовок письма в читаемую строку."""
    if not value:
        return ''
    parts = decode_header(value)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            result.append(part)
    return ''.join(result)


def _get_email_body(msg):
    """Извлекает текстовое тело письма."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == 'text/plain':
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or 'utf-8'
                return payload.decode(charset, errors='replace')
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or 'utf-8'
        return payload.decode(charset, errors='replace') if payload else ''
    return ''


@shared_task
def poll_site_email(site_id):
    """Опрашивает IMAP ящик одного сайта и создаёт чаты/сообщения из новых писем."""
    from .models import Chat, Contact, Message
    from apps.sites.models import Site
    from .services import notify_new_chat, notify_new_message
    from .tasks import assign_chat_to_next_manager

    try:
        site = Site.objects.get(pk=site_id, email_enabled=True)
    except Site.DoesNotExist:
        return

    if not site.email_imap_user or not site.email_imap_password:
        return

    try:
        ctx = ssl.create_default_context()
        imap = imaplib.IMAP4_SSL(site.email_imap_host, site.email_imap_port, ssl_context=ctx)
        imap.login(site.email_imap_user, site.email_imap_password)
        imap.select('INBOX')

        # Ищем непрочитанные письма
        _, data = imap.search(None, 'UNSEEN')
        uid_list = data[0].split()

        for uid in uid_list:
            _, msg_data = imap.fetch(uid, '(RFC822)')
            raw = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw)

            sender_raw = msg.get('From', '')
            sender_name, sender_email = parseaddr(sender_raw)
            sender_name = _decode_header_value(sender_name) or sender_email
            subject = _decode_header_value(msg.get('Subject', '(без темы)'))
            message_id = msg.get('Message-ID', '').strip()
            in_reply_to = msg.get('In-Reply-To', '').strip()
            references = msg.get('References', '').strip()
            thread_id = references.split()[0] if references else (in_reply_to or message_id)
            body = _get_email_body(msg).strip()

            if not sender_email or not body:
                imap.store(uid, '+FLAGS', '\\Seen')
                continue

            # Находим или создаём Contact
            contact, _ = Contact.objects.get_or_create(
                site=site,
                email=sender_email.lower(),
                defaults={'name': sender_name},
            )
            if not contact.name and sender_name:
                contact.name = sender_name
                contact.save(update_fields=['name'])

            # Ищем существующий открытый чат по thread_id
            chat = None
            if thread_id:
                chat = Chat.objects.filter(
                    site=site,
                    channel=Chat.Channel.EMAIL,
                    email_thread_id=thread_id,
                ).exclude(status=Chat.Status.CLOSED).first()

            if not chat:
                chat = Chat.objects.create(
                    site=site,
                    contact=contact,
                    client_name=sender_name,
                    client_email=sender_email.lower(),
                    channel=Chat.Channel.EMAIL,
                    email_subject=subject,
                    email_thread_id=thread_id or message_id,
                    email_message_id=message_id,
                    status=Chat.Status.NEW,
                )
                notify_new_chat(chat)
                assign_chat_to_next_manager.delay(chat.id)
            else:
                chat.email_message_id = message_id
                chat.save(update_fields=['email_message_id', 'updated_at'])

            # Создаём сообщение
            message = Message.objects.create(
                chat=chat,
                sender_type=Message.SenderType.CLIENT,
                content=body,
            )
            notify_new_message(message)

            # Помечаем письмо прочитанным
            imap.store(uid, '+FLAGS', '\\Seen')

        imap.logout()
    except Exception:
        pass  # не роняем Celery при проблемах с IMAP


@shared_task
def poll_all_email_inboxes():
    """Запускается по расписанию — опрашивает все активные email-сайты."""
    from apps.sites.models import Site
    site_ids = list(Site.objects.filter(email_enabled=True).values_list('id', flat=True))
    for site_id in site_ids:
        poll_site_email.delay(site_id)


def send_email_reply(chat, text):
    """Отправляет email-ответ менеджера клиенту через SMTP сайта."""
    site = chat.site
    if not site.email_imap_user or not site.email_imap_password:
        raise ValueError('Email не настроен для этого сайта.')

    msg = MIMEMultipart()
    msg['From'] = site.email_imap_user
    msg['To'] = chat.client_email
    msg['Subject'] = f'Re: {chat.email_subject}'
    msg['Message-ID'] = make_msgid()

    if chat.email_message_id:
        msg['In-Reply-To'] = chat.email_message_id
        msg['References'] = chat.email_thread_id or chat.email_message_id

    msg.attach(MIMEText(text, 'plain', 'utf-8'))

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(site.email_smtp_host, site.email_smtp_port, context=ctx) as smtp:
        smtp.login(site.email_imap_user, site.email_imap_password)
        smtp.sendmail(site.email_imap_user, chat.client_email, msg.as_bytes())


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
