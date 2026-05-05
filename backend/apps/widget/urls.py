from django.urls import path

from .views import (
    WidgetChatHistoryView,
    WidgetChatView,
    WidgetConfigView,
    WidgetMessagesView,
)

urlpatterns = [
    path('<uuid:site_uuid>/config/', WidgetConfigView.as_view(), name='widget-config'),
    path('<uuid:site_uuid>/chat/', WidgetChatView.as_view(), name='widget-chat'),
    path('<uuid:site_uuid>/history/', WidgetChatHistoryView.as_view(), name='widget-history'),
    path('<uuid:site_uuid>/chat/<int:chat_id>/messages/', WidgetMessagesView.as_view(), name='widget-messages'),
]
