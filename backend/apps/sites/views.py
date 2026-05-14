from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.users.permissions import IsAdmin

from .models import Site
from .serializers import SiteSerializer


class SiteViewSet(viewsets.ModelViewSet):
    serializer_class = SiteSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        org_name = self.request.user.organization_name
        if org_name:
            return Site.objects.filter(owner__organization_name=org_name)
        return Site.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['get'], url_path='widget-code')
    def widget_code(self, request, pk=None):
        site = self.get_object()
        api_base = request.build_absolute_uri('/').rstrip('/')
        code = (
            f'<script src="{api_base}/static/widget/widget.js" '
            f'data-site-id="{site.site_uuid}"></script>'
        )
        return Response({'embed_code': code})
