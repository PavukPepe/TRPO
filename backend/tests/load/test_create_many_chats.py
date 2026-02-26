def test_create_many_chats(db, django_user_model):
    user = django_user_model.objects.create_user(email='bulk@e.com', password='p', first_name='Bulk')
    # lightweight load-like test: create many chats and ensure count
    from apps.sites.models import Site
    from apps.chats.models import Chat

    site = Site.objects.create(owner=user, name='BulkSite', url='https://bulk')
    n = 200
    for i in range(n):
        Chat.objects.create(site=site, client_name=f'C{i}')

    assert Chat.objects.filter(site=site).count() == n
