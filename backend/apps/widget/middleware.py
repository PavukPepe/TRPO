from django.http import HttpResponse


class WidgetCORSMiddleware:
    """
    Добавляет CORS-заголовки для публичных эндпоинтов виджета (/api/widget/).
    Позволяет встраивать виджет на любой сайт.
    Должен стоять ДО corsheaders.middleware.CorsMiddleware в MIDDLEWARE,
    чтобы выполняться ПОСЛЕ него при обработке ответа (bottom-up).
    """

    WIDGET_PREFIX = '/api/widget/'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Обработка OPTIONS preflight — возвращаем 200 сразу, не дожидаясь view
        if request.method == 'OPTIONS' and request.path.startswith(self.WIDGET_PREFIX):
            response = HttpResponse(status=200)
            self._add_cors_headers(request, response)
            return response

        response = self.get_response(request)

        if request.path.startswith(self.WIDGET_PREFIX):
            self._add_cors_headers(request, response)

        return response

    @staticmethod
    def _add_cors_headers(request, response):
        origin = request.META.get('HTTP_ORIGIN', '*')
        response['Access-Control-Allow-Origin'] = origin
        response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type'
        response['Access-Control-Allow-Credentials'] = 'false'
        response['Access-Control-Max-Age'] = '86400'
        # Убираем Vary: Origin, который мог добавить django-cors-headers
        # чтобы браузер не кешировал отказ
        if 'Vary' in response:
            vary = response['Vary']
            parts = [p.strip() for p in vary.split(',') if p.strip().lower() != 'origin']
            if parts:
                response['Vary'] = ', '.join(parts)
            else:
                del response['Vary']
