import importlib


def test_widget_middleware_exists():
    mod = importlib.import_module('apps.widget.middleware')
    assert len([n for n in dir(mod) if not n.startswith('_')]) > 0
