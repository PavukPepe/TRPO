from django.urls import path

from .views import (
    ChatsTimelineView,
    ManagerStatsView,
    OverviewStatsView,
    RatingsStatsView,
    SiteStatsView,
)

urlpatterns = [
    path('overview/', OverviewStatsView.as_view(), name='stats-overview'),
    path('managers/', ManagerStatsView.as_view(), name='stats-managers'),
    path('sites/', SiteStatsView.as_view(), name='stats-sites'),
    path('timeline/', ChatsTimelineView.as_view(), name='stats-timeline'),
    path('ratings/', RatingsStatsView.as_view(), name='stats-ratings'),
]
