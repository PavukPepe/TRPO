from apps.sites.models import Site


def test_save_generates_referral(db, django_user_model):
    u = django_user_model.objects.create_user(email='owner@e.com', password='p', first_name='Owner')
    s = Site.objects.create(owner=u, name='X', url='https://x.com', telegram_referral_code='')
    assert s.telegram_referral_code
    assert len(s.telegram_referral_code) == 12
