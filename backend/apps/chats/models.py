from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Contact(models.Model):
    """Контакт — уникальный человек, к которому привязаны все лиды (чаты)."""
    site = models.ForeignKey(
        'sites.Site',
        on_delete=models.CASCADE,
        related_name='contacts',
        verbose_name='Сайт',
    )
    name = models.CharField('Имя', max_length=255, blank=True)
    email = models.EmailField('Email', blank=True, db_index=True)
    phone = models.CharField('Телефон', max_length=50, blank=True)
    telegram_username = models.CharField('Telegram', max_length=255, blank=True)
    notes = models.TextField('Заметки', blank=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлён', auto_now=True)

    class Meta:
        verbose_name = 'Контакт'
        verbose_name_plural = 'Контакты'
        ordering = ['-updated_at']
        unique_together = [('site', 'email')]

    def __str__(self):
        return self.name or self.email or f'Контакт #{self.pk}'


class Chat(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Новая'
        IN_PROGRESS = 'in_progress', 'В обработке'
        REPLIED = 'replied', 'Общались ранее'
        CLOSED = 'closed', 'Закрыта'

    class Channel(models.TextChoices):
        WIDGET = 'widget', 'Виджет'
        TELEGRAM = 'telegram', 'Telegram'
        EMAIL = 'email', 'Email'

    site = models.ForeignKey(
        'sites.Site',
        on_delete=models.CASCADE,
        related_name='chats',
        verbose_name='Сайт',
    )
    contact = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chats',
        verbose_name='Контакт',
    )
    client_name = models.CharField('Имя клиента', max_length=255, blank=True)
    client_email = models.EmailField('Email клиента', blank=True)
    telegram_username = models.CharField('Telegram никнейм', max_length=255, blank=True)

    # Email threading fields
    email_subject = models.CharField('Тема письма', max_length=500, blank=True)
    email_thread_id = models.CharField('Thread-ID', max_length=500, blank=True, db_index=True)
    email_message_id = models.CharField('Message-ID последнего письма', max_length=500, blank=True)

    assigned_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_chats',
        verbose_name='Ответственный менеджер',
    )
    status = models.CharField(
        'Статус',
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )
    channel = models.CharField(
        'Канал',
        max_length=10,
        choices=Channel.choices,
        default=Channel.WIDGET,
    )
    telegram_user_id = models.BigIntegerField(
        'Telegram User ID', null=True, blank=True, db_index=True,
    )
    telegram_chat_id = models.BigIntegerField(
        'Telegram Chat ID', null=True, blank=True, db_index=True,
    )
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)
    updated_at = models.DateTimeField('Дата обновления', auto_now=True)
    closed_at = models.DateTimeField('Дата закрытия', null=True, blank=True)

    class Meta:
        verbose_name = 'Заявка'
        verbose_name_plural = 'Заявки'
        ordering = ['-updated_at']

    def __str__(self):
        return f'Заявка #{self.pk} — {self.client_name or "Без имени"}'


class Message(models.Model):
    class SenderType(models.TextChoices):
        CLIENT = 'client', 'Клиент'
        MANAGER = 'manager', 'Менеджер'
        SYSTEM = 'system', 'Система'

    chat = models.ForeignKey(
        Chat,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Чат',
    )
    sender_type = models.CharField(
        'Тип отправителя',
        max_length=10,
        choices=SenderType.choices,
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_messages',
        verbose_name='Отправитель',
    )
    content = models.TextField('Содержание', blank=True)
    timestamp = models.DateTimeField('Время отправки', auto_now_add=True)

    class Meta:
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'
        ordering = ['timestamp']

    def __str__(self):
        return f'[{self.sender_type}] {self.content[:50]}'


class File(models.Model):
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name='files',
        verbose_name='Сообщение',
    )
    file = models.FileField('Файл', upload_to='chat_files/%Y/%m/')
    filename = models.CharField('Имя файла', max_length=255)
    file_size = models.PositiveIntegerField('Размер файла (байт)', default=0)
    mime_type = models.CharField('MIME-тип', max_length=100, blank=True)
    uploaded_at = models.DateTimeField('Дата загрузки', auto_now_add=True)

    class Meta:
        verbose_name = 'Файл'
        verbose_name_plural = 'Файлы'

    def __str__(self):
        return self.filename


class Rating(models.Model):
    chat = models.OneToOneField(
        Chat,
        on_delete=models.CASCADE,
        related_name='rating',
        verbose_name='Заявка',
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ratings',
        verbose_name='Менеджер',
    )
    rating = models.PositiveSmallIntegerField(
        'Оценка',
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField('Комментарий', blank=True)
    created_at = models.DateTimeField('Дата оценки', auto_now_add=True)

    class Meta:
        verbose_name = 'Оценка'
        verbose_name_plural = 'Оценки'

    def __str__(self):
        return f'Оценка {self.rating}/5 для {self.manager}'


class Template(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='templates',
        verbose_name='Пользователь',
        help_text='NULL = общий шаблон для всех',
    )
    title = models.CharField('Название', max_length=255)
    content = models.TextField('Содержание')
    hotkey = models.CharField('Горячая клавиша', max_length=50, blank=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        verbose_name = 'Шаблон ответа'
        verbose_name_plural = 'Шаблоны ответов'
        ordering = ['title']

    def __str__(self):
        return self.title


class ManagerQueue(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_queue',
        verbose_name='Владелец (админ)',
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='queue_position',
        verbose_name='Менеджер',
    )
    position = models.PositiveIntegerField('Позиция в очереди', default=0)
    is_active = models.BooleanField('Активен в очереди', default=True)

    class Meta:
        verbose_name = 'Очередь менеджеров'
        verbose_name_plural = 'Очередь менеджеров'
        ordering = ['position']
        unique_together = ('owner', 'manager')

    def __str__(self):
        return f'{self.manager} — позиция {self.position}'


class ManagerStatus(models.Model):
    class Status(models.TextChoices):
        ONLINE = 'online', 'Онлайн'
        AWAY = 'away', 'Отошёл'
        OFFLINE = 'offline', 'Оффлайн'

    manager = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='manager_status',
        verbose_name='Менеджер',
    )
    status = models.CharField(
        'Статус',
        max_length=10,
        choices=Status.choices,
        default=Status.OFFLINE,
    )
    changed_at = models.DateTimeField('Время изменения', auto_now=True)

    class Meta:
        verbose_name = 'Статус менеджера'
        verbose_name_plural = 'Статусы менеджеров'

    def __str__(self):
        return f'{self.manager} — {self.status}'
