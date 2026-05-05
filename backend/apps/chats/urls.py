from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ChatViewSet,
    ContactViewSet,
    HeartbeatView,
    ManagerQueueUpdateView,
    ManagerQueueView,
    ManagerStatusView,
    MessageListCreateView,
    RatingCreateView,
    TemplateViewSet,
)

router = DefaultRouter()
router.register('', ChatViewSet, basename='chats')

templates_router = DefaultRouter()
templates_router.register('', TemplateViewSet, basename='templates')

contacts_router = DefaultRouter()
contacts_router.register('', ContactViewSet, basename='contacts')

urlpatterns = [
    # Heartbeat (before router to avoid catch-all)
    path('heartbeat/', HeartbeatView.as_view(), name='heartbeat'),
    # Manager status
    path('my-status/', ManagerStatusView.as_view(), name='manager-status'),
    # Manager queue
    path('queue/', ManagerQueueView.as_view(), name='manager-queue'),
    path('queue/<int:pk>/', ManagerQueueUpdateView.as_view(), name='manager-queue-update'),
    # Rating
    path('ratings/', RatingCreateView.as_view(), name='rating-create'),
    # Templates
    path('templates/', include(templates_router.urls)),
    # Messages
    path('<int:chat_id>/messages/', MessageListCreateView.as_view(), name='chat-messages'),
    # Chats (router last — it has empty prefix)
    path('', include(router.urls)),
]
