from django.test import RequestFactory
from django.http import HttpResponse
from apps.widget.middleware import WidgetCORSMiddleware


def test_options_preflight_returns_200_and_headers():
    rf = RequestFactory()
    req = rf.options('/api/widget/foo')
    req.META['HTTP_ORIGIN'] = 'https://origin.example'

    mw = WidgetCORSMiddleware(lambda r: HttpResponse('ok'))
    resp = mw(req)
    assert resp.status_code == 200
    assert resp['Access-Control-Allow-Origin'] == 'https://origin.example'


def test_adds_cors_headers_on_widget_path():
    rf = RequestFactory()
    req = rf.get('/api/widget/data')
    req.META['HTTP_ORIGIN'] = 'https://a'

    def inner(r):
        res = HttpResponse('ok')
        res['Vary'] = 'Origin, Accept'
        return res

    mw = WidgetCORSMiddleware(inner)
    resp = mw(req)
    assert resp['Access-Control-Allow-Methods']
    assert 'Origin' not in resp.get('Vary', '')
