from django.contrib import admin

from .models import Chat, File, ManagerQueue, ManagerStatus, Message, Rating, Template


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ('sender_type', 'sender', 'content', 'timestamp')


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ('id', 'client_name', 'site', 'assigned_manager', 'status', 'channel', 'created_at')
    list_filter = ('status', 'channel', 'site')
    search_fields = ('client_name', 'telegram_username')
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat', 'sender_type', 'content_short', 'timestamp')
    list_filter = ('sender_type',)

    def content_short(self, obj):
        return obj.content[:80]
    content_short.short_description = 'Содержание'


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ('filename', 'message', 'file_size', 'mime_type', 'uploaded_at')


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ('chat', 'manager', 'rating', 'created_at')
    list_filter = ('rating',)


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'hotkey', 'created_at')
    list_filter = ('user',)


@admin.register(ManagerQueue)
class ManagerQueueAdmin(admin.ModelAdmin):
    list_display = ('manager', 'owner', 'position', 'is_active')
    list_filter = ('is_active',)


@admin.register(ManagerStatus)
class ManagerStatusAdmin(admin.ModelAdmin):
    list_display = ('manager', 'status', 'changed_at')
    list_filter = ('status',)
