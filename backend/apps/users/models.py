import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email обязателен')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        return self.create_user(email, password, **extra_fields)


PLAN_LIMITS = {
    'starter': {
        'name': 'Старт',
        'price': 0,
        'sites': 1,
        'managers': 5,
        'channels': ['widget', 'telegram'],
        'analytics': False,
        'email_channel': False,
        'api_access': False,
    },
    'business': {
        'name': 'Бизнес',
        'price': 2990,
        'sites': 5,
        'managers': 25,
        'channels': ['widget', 'telegram', 'email'],
        'analytics': True,
        'email_channel': True,
        'api_access': False,
    },
    'enterprise': {
        'name': 'Корпоратив',
        'price': 9990,
        'sites': 999,
        'managers': 999,
        'channels': ['widget', 'telegram', 'email'],
        'analytics': True,
        'email_channel': True,
        'api_access': True,
    },
}


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Администратор'
        ROP = 'rop', 'Руководитель отдела продаж'
        MANAGER = 'manager', 'Менеджер'

    class Plan(models.TextChoices):
        STARTER = 'starter', 'Старт'
        BUSINESS = 'business', 'Бизнес'
        ENTERPRISE = 'enterprise', 'Корпоратив'

    username = None
    email = models.EmailField('Email', unique=True)
    role = models.CharField('Роль', max_length=10, choices=Role.choices, default=Role.MANAGER)
    plan = models.CharField('Тариф', max_length=20, choices=Plan.choices, default=Plan.STARTER)
    organization_name = models.CharField('Название организации', max_length=255, blank=True)
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name']

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.first_name} ({self.email})'

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_rop(self):
        return self.role == self.Role.ROP

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER


class InvitationToken(models.Model):
    class Purpose(models.TextChoices):
        INVITE = 'invite', 'Приглашение'
        RESET = 'reset', 'Сброс пароля'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='invitation_tokens',
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    purpose = models.CharField(max_length=10, choices=Purpose.choices)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Токен приглашения'
        verbose_name_plural = 'Токены приглашений'

    def is_valid(self):
        return not self.used and self.expires_at > timezone.now()

    @classmethod
    def create_for_user(cls, user, purpose):
        hours = (
            settings.INVITE_TOKEN_EXPIRE_HOURS
            if purpose == cls.Purpose.INVITE
            else settings.RESET_TOKEN_EXPIRE_HOURS
        )
        # инвалидируем предыдущие токены того же типа
        cls.objects.filter(user=user, purpose=purpose, used=False).update(used=True)
        return cls.objects.create(
            user=user,
            purpose=purpose,
            expires_at=timezone.now() + timedelta(hours=hours),
        )
