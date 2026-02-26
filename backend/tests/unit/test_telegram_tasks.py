import json
from apps.telegram import tasks
from apps.sites.models import Site
from apps.chats.models import Chat


class DummyResp:
    def __init__(self, ok=True, text='ok'):
        self._ok = ok
        self.text = text

    def json(self):
        return {'ok': self._ok}


def test_send_telegram_reply_posts(monkeypatch, db, django_user_model):
    owner = django_user_model.objects.create_user(email='o@e.com', password='p', first_name='O')
    site = Site.objects.create(owner=owner, name='S', url='https://s', telegram_bot_token='tok')
    chat = Chat.objects.create(site=site, telegram_chat_id=12345)

    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        return DummyResp(ok=True)

    monkeypatch.setattr('apps.telegram.tasks.requests.post', fake_post)

    tasks.send_telegram_reply(chat.id, 'hello')
    assert any('sendMessage' in c[0] for c in calls)


def test_handle_rating_callback_creates_rating_and_calls_api(monkeypatch, db, django_user_model):
    owner = django_user_model.objects.create_user(email='o2@e.com', password='p', first_name='O')
    manager = django_user_model.objects.create_user(email='m2@e.com', password='p', first_name='M')
    site = Site.objects.create(owner=owner, name='S2', url='https://s2', telegram_bot_token='tok')
    chat = Chat.objects.create(site=site, assigned_manager=manager, telegram_chat_id=999)

    posted = []

    def fake_post(url, json=None, timeout=None):
        posted.append((url, json))
        return DummyResp(ok=True)

    monkeypatch.setattr('apps.telegram.tasks.requests.post', fake_post)

    callback_query = {
        'id': 'cb1',
        'data': json.dumps({'action': 'rate', 'chat_id': chat.id, 'rating': 4}),
        'message': {'chat': {'id': 999}, 'message_id': 77}
    }

    tasks.handle_rating_callback(site.id, callback_query)

    from apps.chats.models import Rating
    assert Rating.objects.filter(chat=chat).exists()
    assert any('answerCallbackQuery' in p[0] or 'editMessageText' in p[0] for p in posted)
