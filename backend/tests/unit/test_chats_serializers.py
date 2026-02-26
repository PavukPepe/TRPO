from apps.chats.serializers import ChatListSerializer
from apps.sites.models import Site
from apps.chats.models import Chat, Message


def test_chat_list_serializer_last_message_and_manager(db, django_user_model):
    user = django_user_model.objects.create_user(email='a@e.com', password='p', first_name='Anna')
    site = Site.objects.create(owner=user, name='S', url='https://s')
    manager = django_user_model.objects.create_user(email='mgr@e.com', password='p', first_name='M')

    chat = Chat.objects.create(site=site, client_name='C', assigned_manager=manager)
    Message.objects.create(chat=chat, sender_type=Message.SenderType.CLIENT, content='first')
    Message.objects.create(chat=chat, sender_type=Message.SenderType.MANAGER, sender=manager, content='reply')

    data = ChatListSerializer(chat).data
    assert data['manager_name'] == 'M'
    assert data['last_message']['content'].startswith('reply')
