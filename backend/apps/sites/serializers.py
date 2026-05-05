from rest_framework import serializers

from .models import Site


class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Site
        fields = (
            'id', 'name', 'url', 'site_uuid',
            'widget_settings', 'working_hours',
            'auto_reply_enabled', 'auto_reply_message',
            'telegram_bot_token', 'telegram_referral_code',
            'email_enabled',
            'email_imap_host', 'email_imap_port', 'email_imap_user', 'email_imap_password',
            'email_smtp_host', 'email_smtp_port',
            'created_at',
        )
        read_only_fields = ('id', 'site_uuid', 'telegram_referral_code', 'created_at')
        extra_kwargs = {
            'email_imap_password': {'write_only': True},
        }


class SiteWidgetCodeSerializer(serializers.Serializer):
    embed_code = serializers.CharField(read_only=True)
