from django.contrib import admin

from .models import Site


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'owner', 'site_uuid', 'auto_reply_enabled', 'created_at')
    list_filter = ('auto_reply_enabled',)
    search_fields = ('name', 'url')
    readonly_fields = ('site_uuid', 'telegram_referral_code', 'created_at')
