from apps.sites.serializers import SiteSerializer, SiteWidgetCodeSerializer
from apps.sites.models import Site


def test_site_serializer_read_only_fields(db, django_user_model):
    u = django_user_model.objects.create_user(email='s@e.com', password='p', first_name='S')
    s = Site.objects.create(owner=u, name='N', url='https://n')
    data = SiteSerializer(s).data
    assert 'site_uuid' in data
    assert 'telegram_referral_code' in data


def test_widget_code_serializer():
    ser = SiteWidgetCodeSerializer({})
    assert 'embed_code' in ser.fields
