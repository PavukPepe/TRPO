from rest_framework.test import APIRequestFactory
from apps.stats.views import ManagerStatsView
from apps.sites.models import Site
from apps.chats.models import Chat, Message


def test_manager_avg_response_time(db, django_user_model):
    factory = APIRequestFactory()
    manager = django_user_model.objects.create_user(email='mgr@e.com', password='p', first_name='Mgr', role='manager')
    owner = django_user_model.objects.create_user(email='own@e.com', password='p', first_name='Own')
    site = Site.objects.create(owner=owner, name='S', url='https://s')

    chat = Chat.objects.create(site=site, assigned_manager=manager)

    m1 = Message.objects.create(chat=chat, sender_type=Message.SenderType.CLIENT, content='hi')
    m2 = Message.objects.create(chat=chat, sender_type=Message.SenderType.MANAGER, sender=manager, content='ok')

    from django.utils import timezone
    t1 = timezone.now()
    t2 = t1 + timezone.timedelta(seconds=30)
    Message.objects.filter(pk=m1.pk).update(timestamp=t1)
    Message.objects.filter(pk=m2.pk).update(timestamp=t2)

    req = factory.get('/api/stats/manager/')
    req.user = manager

    view = ManagerStatsView.as_view()
    resp = view(req)
    assert resp.status_code == 200
    data = resp.data
    found = [r for r in data if r['id'] == manager.id]
    assert found
    assert found[0]['avg_response_time'] in (30, 30.0)
