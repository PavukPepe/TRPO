from rest_framework.test import APIRequestFactory
from apps.chats.views import ChatViewSet
from apps.sites.models import Site
from apps.chats.models import Chat


def test_assign_manager_and_status_change(db, django_user_model, monkeypatch):
    factory = APIRequestFactory()
    owner = django_user_model.objects.create_user(email='o@e', password='p', first_name='O', role='admin')
    manager = django_user_model.objects.create_user(email='m@e', password='p', first_name='M', role='manager')
    site = Site.objects.create(owner=owner, name='S', url='https://s')
    chat = Chat.objects.create(site=site)

    # assign manager
    req = factory.put(f'/api/chats/{chat.id}/assign/', {'manager_id': manager.id}, format='json')
    req.user = owner
    view = ChatViewSet.as_view({'put': 'assign_manager'})
    resp = view(req, pk=chat.id)
    assert resp.status_code == 200
    chat.refresh_from_db()
    assert chat.assigned_manager_id == manager.id

    # change status to closed
    req2 = factory.put(f'/api/chats/{chat.id}/status/', {'status': Chat.Status.CLOSED}, format='json')
    req2.user = owner
    view2 = ChatViewSet.as_view({'put': 'change_status'})
    resp2 = view2(req2, pk=chat.id)
    assert resp2.status_code == 200
    chat.refresh_from_db()
    assert chat.status == Chat.Status.CLOSED
