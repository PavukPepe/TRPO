from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    # API
    path('api/auth/', include('apps.users.urls_auth')),
    path('api/users/', include('apps.users.urls')),
    path('api/sites/', include('apps.sites.urls')),
    path('api/chats/', include('apps.chats.urls')),
    path('api/stats/', include('apps.stats.urls')),
    path('api/telegram/', include('apps.telegram.urls')),
    path('api/widget/', include('apps.widget.urls')),
    # Swagger
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
