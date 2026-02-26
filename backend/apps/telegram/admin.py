from django.contrib import admin

from .models import TelegramUser


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'username', 'first_name', 'last_name', 'created_at')
    search_fields = ('username', 'first_name', 'telegram_id')
    readonly_fields = ('created_at',)
