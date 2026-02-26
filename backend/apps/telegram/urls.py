from django.urls import path

from .views import TelegramWebhookView

urlpatterns = [
    path('webhook/<uuid:site_uuid>/', TelegramWebhookView.as_view(), name='telegram-webhook'),
]
