from django.urls import path

from .views import ChatsTimelineView, ManagerStatsView, OverviewStatsView, RatingsStatsView

urlpatterns = [
    path('overview/', OverviewStatsView.as_view(), name='stats-overview'),
    path('managers/', ManagerStatsView.as_view(), name='stats-managers'),
    path('timeline/', ChatsTimelineView.as_view(), name='stats-timeline'),
    path('ratings/', RatingsStatsView.as_view(), name='stats-ratings'),
]
