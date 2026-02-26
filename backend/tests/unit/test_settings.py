from django.conf import settings


def test_settings_loaded():
    assert hasattr(settings, "INSTALLED_APPS")
    assert isinstance(settings.INSTALLED_APPS, (list, tuple))
