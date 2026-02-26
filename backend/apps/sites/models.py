import uuid

from django.conf import settings
from django.db import models


class Site(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sites',
        verbose_name='Владелец',
    )
    name = models.CharField('Название сайта', max_length=255)
    url = models.URLField('URL сайта')
    site_uuid = models.UUIDField('UUID сайта', default=uuid.uuid4, unique=True, editable=False)

    # Widget settings
    widget_settings = models.JSONField('Настройки виджета', default=dict, blank=True)
    # Expected: { "color": "#4F46E5", "position": "bottom-right", "greeting_text": "Здравствуйте!", "require_telegram": true }

    # Working hours
    working_hours = models.JSONField('Рабочие часы', default=dict, blank=True)
    # Expected: { "start": "09:00", "end": "18:00", "timezone": "Europe/Moscow" }

    # Auto-reply
    auto_reply_enabled = models.BooleanField('Автоответ включён', default=False)
    auto_reply_message = models.TextField('Сообщение автоответа', blank=True)

    # Telegram
    telegram_bot_token = models.CharField('Telegram Bot Token', max_length=255, blank=True)
    telegram_referral_code = models.CharField(
        'Реферальный код Telegram',
        max_length=50,
        unique=True,
        blank=True,
    )

    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        verbose_name = 'Сайт'
        verbose_name_plural = 'Сайты'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.telegram_referral_code:
            self.telegram_referral_code = uuid.uuid4().hex[:12]
        super().save(*args, **kwargs)
