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
            'created_at',
        )
        read_only_fields = ('id', 'site_uuid', 'telegram_referral_code', 'created_at')


class SiteWidgetCodeSerializer(serializers.Serializer):
    embed_code = serializers.CharField(read_only=True)
