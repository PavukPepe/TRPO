from rest_framework import serializers

from apps.chats.models import Chat, File, Message


class WidgetConfigSerializer(serializers.Serializer):
    site_uuid = serializers.UUIDField()
    site_name = serializers.CharField()
    widget_settings = serializers.JSONField()
    working_hours = serializers.JSONField()
    auto_reply_enabled = serializers.BooleanField()
    auto_reply_message = serializers.CharField()


class WidgetChatCreateSerializer(serializers.Serializer):
    client_name = serializers.CharField(max_length=255, required=False, default='')
    client_email = serializers.EmailField(required=False, default='')
    initial_message = serializers.CharField(required=False, default='')


class WidgetChatSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chat
        fields = ('id', 'client_name', 'status', 'created_at')


class WidgetFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = ('id', 'file', 'filename', 'file_size', 'mime_type')


class WidgetMessageSerializer(serializers.ModelSerializer):
    files = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ('id', 'sender_type', 'content', 'timestamp', 'files')

    def get_files(self, obj):
        request = self.context.get('request')
        return WidgetFileSerializer(obj.files.all(), many=True, context={'request': request}).data


class WidgetSendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(required=False, allow_blank=True, default='')
