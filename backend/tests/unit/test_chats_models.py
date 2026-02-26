from django.core.files.uploadedfile import SimpleUploadedFile
from apps.sites.models import Site
from apps.chats.models import Chat, Message, File, Rating, Template, ManagerQueue, ManagerStatus


def test_chat_and_related_str(db, django_user_model):
    user = django_user_model.objects.create_user(email='u@e.com', password='p', first_name='U')
    site = Site.objects.create(owner=user, name='S', url='https://example.com')

    chat = Chat.objects.create(site=site, client_name='Client')
    assert 'Заявка #' in str(chat)

    msg = Message.objects.create(chat=chat, sender_type=Message.SenderType.CLIENT, content='hello')
    assert 'hello' in str(msg)

    f = File.objects.create(
        message=msg,
        file=SimpleUploadedFile('f.txt', b'hi'),
        filename='f.txt',
        file_size=2,
    )
    assert f.filename == 'f.txt'

    manager = django_user_model.objects.create_user(email='m@e.com', password='p', first_name='M')
    rating = Rating.objects.create(chat=chat, manager=manager, rating=5)
    assert '5' in str(rating)

    tpl = Template.objects.create(user=manager, title='T', content='c')
    assert tpl.title == 'T'

    mq = ManagerQueue.objects.create(owner=user, manager=manager, position=1)
    assert 'позиция' in str(mq)

    ms = ManagerStatus.objects.create(manager=manager, status=ManagerStatus.Status.ONLINE)
    assert ms.status == ManagerStatus.Status.ONLINE
