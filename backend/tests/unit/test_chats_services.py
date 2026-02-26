from apps.chats import services
from apps.sites.models import Site
from apps.chats.models import Chat, Message


class DummyLayer:
    def __init__(self):
        self.calls = []

    def group_send(self, group, message):
        self.calls.append((group, message))


def test_notify_new_chat_calls_group_send(db, django_user_model, monkeypatch):
    user = django_user_model.objects.create_user(email='u2@e.com', password='p', first_name='U')
    site = Site.objects.create(owner=user, name='S2', url='https://ex2.com')
    chat = Chat.objects.create(site=site, client_name='C')

    layer = DummyLayer()
    monkeypatch.setattr(services, 'get_layer', lambda: layer)

    services.notify_new_chat(chat)
    assert any('notifications_broadcast' == g for g, _ in layer.calls)


def test_notify_new_message_groups(db, django_user_model, monkeypatch):
    user = django_user_model.objects.create_user(email='u3@e.com', password='p', first_name='U')
    manager = django_user_model.objects.create_user(email='m3@e.com', password='p', first_name='M')
    site = Site.objects.create(owner=user, name='S3', url='https://ex3.com')
    chat = Chat.objects.create(site=site, client_name='C3', assigned_manager=manager)

    msg = Message.objects.create(chat=chat, sender_type=Message.SenderType.CLIENT, content='hey')

    layer = DummyLayer()
    monkeypatch.setattr(services, 'get_layer', lambda: layer)

    services.notify_new_message(msg)
    groups = [g for g, _ in layer.calls]
    assert f'chat_{chat.id}' in groups
    assert f'notifications_{manager.id}' in groups
