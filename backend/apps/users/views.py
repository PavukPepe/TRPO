from django.contrib.auth import get_user_model
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from .permissions import IsAdmin
from .serializers import (
    ChangePasswordSerializer,
    ProfileSerializer,
    RegisterSerializer,
    UserCreateSerializer,
    UserSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not request.user.check_password(serializer.validated_data['old_password']):
            return Response(
                {'old_password': 'Неверный текущий пароль'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()
        return Response({'detail': 'Пароль успешно изменён'})


class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        org_name = self.request.user.organization_name
        if org_name:
            return User.objects.filter(organization_name=org_name)
        return User.objects.all()

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    def perform_create(self, serializer):
        serializer.save(organization_name=self.request.user.organization_name)

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        user = self.get_object()
        new_password = request.data.get('password', '').strip()
        if len(new_password) < 8:
            raise ValidationError({'password': 'Пароль должен содержать минимум 8 символов.'})
        user.set_password(new_password)
        user.save()
        return Response({'detail': 'Пароль успешно сброшен.'})
