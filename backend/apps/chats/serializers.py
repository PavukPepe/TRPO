from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Chat, File, ManagerQueue, ManagerStatus, Message, Rating, Template

User = get_user_model()


# --- Chat ---

class MessageSerializer(serializers.ModelSerializer):
    files = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ('id', 'chat', 'sender_type', 'sender', 'content', 'timestamp', 'files')
        read_only_fields = ('id', 'timestamp', 'files')

    def get_files(self, obj):
        request = self.context.get('request')
        return FileSerializer(obj.files.all(), many=True, context={'request': request}).data


class MessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ('content',)
        extra_kwargs = {
            'content': {'required': False, 'allow_blank': True, 'default': ''},
        }


class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = ('id', 'file', 'filename', 'file_size', 'mime_type', 'uploaded_at')
        read_only_fields = ('id', 'filename', 'file_size', 'mime_type', 'uploaded_at')


class ChatListSerializer(serializers.ModelSerializer):
    site_name = serializers.CharField(source='site.name', read_only=True)
    manager_name = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = (
            'id', 'client_name', 'client_email', 'telegram_username',
            'status', 'channel', 'site', 'site_name',
            'assigned_manager', 'manager_name',
            'last_message', 'unread_count',
            'created_at', 'updated_at', 'closed_at',
        )

    def get_manager_name(self, obj):
        if obj.assigned_manager:
            return obj.assigned_manager.first_name
        return None

    def get_last_message(self, obj):
        msg = obj.messages.order_by('-timestamp').first()
        if msg:
            return {'content': msg.content[:100], 'timestamp': msg.timestamp, 'sender_type': msg.sender_type}
        return None

    def get_unread_count(self, obj):
        return 0  # TODO: реализовать при добавлении отметок прочтения


class ChatDetailSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    site_name = serializers.CharField(source='site.name', read_only=True)
    manager_name = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = (
            'id', 'client_name', 'client_email', 'telegram_username',
            'status', 'channel', 'site', 'site_name',
            'assigned_manager', 'manager_name',
            'messages',
            'created_at', 'updated_at', 'closed_at',
        )

    def get_manager_name(self, obj):
        if obj.assigned_manager:
            return obj.assigned_manager.first_name
        return None


class ChatCreateSerializer(serializers.ModelSerializer):
    initial_message = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Chat
        fields = ('site', 'client_name', 'client_email', 'telegram_username', 'channel', 'initial_message')

    def create(self, validated_data):
        initial_message = validated_data.pop('initial_message', None)
        chat = Chat.objects.create(**validated_data)
        if initial_message:
            Message.objects.create(
                chat=chat,
                sender_type=Message.SenderType.CLIENT,
                content=initial_message,
            )
        return chat


class ChatAssignSerializer(serializers.Serializer):
    manager_id = serializers.IntegerField()

    def validate_manager_id(self, value):
        try:
            User.objects.get(pk=value, role__in=['manager', 'rop', 'admin'], is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError('Менеджер не найден или неактивен')
        return value


class ChatStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Chat.Status.choices)


class ChatMergeSerializer(serializers.Serializer):
    target_chat_id = serializers.IntegerField()

    def validate_target_chat_id(self, value):
        try:
            Chat.objects.get(pk=value)
        except Chat.DoesNotExist:
            raise serializers.ValidationError('Целевая заявка не найдена')
        return value


# --- Rating ---

class RatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rating
        fields = ('id', 'chat', 'manager', 'rating', 'comment', 'created_at')
        read_only_fields = ('id', 'created_at')


# --- Template ---

class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = ('id', 'user', 'title', 'content', 'hotkey', 'created_at')
        read_only_fields = ('id', 'created_at')


# --- Manager Queue ---

class ManagerQueueSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source='manager.first_name', read_only=True)
    manager_email = serializers.CharField(source='manager.email', read_only=True)

    class Meta:
        model = ManagerQueue
        fields = ('id', 'manager', 'manager_name', 'manager_email', 'position', 'is_active')
        read_only_fields = ('id',)


# --- Manager Status ---

class ManagerStatusSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source='manager.first_name', read_only=True)

    class Meta:
        model = ManagerStatus
        fields = ('id', 'manager', 'manager_name', 'status', 'changed_at')
        read_only_fields = ('id', 'changed_at')
