from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


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


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Администратор'
        ROP = 'rop', 'Руководитель отдела продаж'
        MANAGER = 'manager', 'Менеджер'

    username = None
    email = models.EmailField('Email', unique=True)
    role = models.CharField('Роль', max_length=10, choices=Role.choices, default=Role.MANAGER)
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
