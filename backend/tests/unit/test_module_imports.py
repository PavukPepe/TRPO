import importlib


MODULES = [
    'apps.users',
    'apps.chats',
    'apps.sites',
    'apps.widget',
    'apps.telegram',
    'apps.stats',
]


def test_apps_importable():
    for mod in MODULES:
        m = importlib.import_module(mod)
        assert hasattr(m, '__name__')
        assert len(dir(m)) > 0
