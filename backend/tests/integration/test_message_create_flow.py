from rest_framework.test import APIRequestFactory
from apps.chats.views import MessageListCreateView
from apps.sites.models import Site
from apps.chats.models import Chat, Message, File
from django.core.files.uploadedfile import SimpleUploadedFile


def test_message_create_auto_assign_and_file_save(db, django_user_model, monkeypatch):
    factory = APIRequestFactory()
    manager = django_user_model.objects.create_user(email='mgr2@e.com', password='p', first_name='Mgr', role='manager')
    owner = django_user_model.objects.create_user(email='own2@e.com', password='p', first_name='Own')
    site = Site.objects.create(owner=owner, name='Sx', url='https://sx')

    chat = Chat.objects.create(site=site)

    # prepare request with a file and authenticated user
    f = SimpleUploadedFile('img.png', b'PNGDATA', content_type='image/png')
    req = factory.post(f'/api/chats/{chat.id}/messages/', {'content': 'reply', 'files': [f]}, format='multipart')
    req.user = manager
    req.FILES.setlist('files', [f])

    view = MessageListCreateView.as_view()
    resp = view(req, chat_id=chat.id)
    assert resp.status_code == 201

    # message should be created and chat assigned
    assert Message.objects.filter(chat=chat).exists()
    chat.refresh_from_db()
    assert chat.assigned_manager_id == manager.id
