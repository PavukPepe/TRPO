from django.db import models


class TelegramUser(models.Model):
    """Маппинг Telegram-пользователя для связки с чатами."""
    telegram_id = models.BigIntegerField('Telegram ID', unique=True, db_index=True)
    username = models.CharField('Username', max_length=255, blank=True)
    first_name = models.CharField('Имя', max_length=255)
    last_name = models.CharField('Фамилия', max_length=255, blank=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    class Meta:
        verbose_name = 'Telegram-пользователь'
        verbose_name_plural = 'Telegram-пользователи'

    def __str__(self):
        return f'@{self.username}' if self.username else f'TG#{self.telegram_id}'
