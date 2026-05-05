from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from .models import InvitationToken, PLAN_LIMITS

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    consent_pdn = serializers.BooleanField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('email', 'password', 'first_name', 'last_name',
                  'organization_name', 'plan', 'consent_pdn')
        extra_kwargs = {'plan': {'required': False}}

    def validate_consent_pdn(self, value):
        if not value:
            raise serializers.ValidationError(
                'Необходимо согласие на обработку персональных данных (ФЗ-152).'
            )
        return value

    def create(self, validated_data):
        validated_data.pop('consent_pdn', None)
        return User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            organization_name=validated_data.get('organization_name', ''),
            plan=validated_data.get('plan', User.Plan.STARTER),
            role=User.Role.ADMIN,
            consent_pdn_at=timezone.now(),
        )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'role',
                  'organization_name', 'plan', 'is_active', 'created_at')
        read_only_fields = ('id', 'created_at')


class UserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'role')

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            password=None,
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            role=validated_data.get('role', User.Role.MANAGER),
            # наследуем организацию и тариф от пригласившего admin-а
            organization_name=validated_data.get('organization_name', ''),
            plan=validated_data.get('plan', User.Plan.STARTER),
        )
        user.is_active = False
        user.save(update_fields=['is_active'])
        return user


class ProfileSerializer(serializers.ModelSerializer):
    plan_limits = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'role',
                  'organization_name', 'plan', 'plan_limits', 'created_at')
        read_only_fields = ('id', 'email', 'role', 'plan', 'created_at')

    def get_plan_limits(self, obj):
        # Менеджеры и РОПы наследуют лимиты от admin-а своей организации
        if obj.role != User.Role.ADMIN and obj.organization_name:
            admin = User.objects.filter(
                organization_name=obj.organization_name,
                role=User.Role.ADMIN,
            ).only('plan').first()
            if admin:
                return PLAN_LIMITS.get(admin.plan, PLAN_LIMITS['starter'])
        return PLAN_LIMITS.get(obj.plan, PLAN_LIMITS['starter'])


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(min_length=8)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class SetPasswordSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    password = serializers.CharField(min_length=8)

    def validate_token(self, value):
        try:
            token = InvitationToken.objects.select_related('user').get(token=value)
        except InvitationToken.DoesNotExist:
            raise serializers.ValidationError('Неверная или устаревшая ссылка.')
        if not token.is_valid():
            raise serializers.ValidationError('Срок действия ссылки истёк.')
        self._token_obj = token
        return value

    def save(self):
        token = self._token_obj
        user = token.user
        user.set_password(self.validated_data['password'])
        user.is_active = True
        user.save(update_fields=['password', 'is_active'])
        token.used = True
        token.save(update_fields=['used'])
        return user
