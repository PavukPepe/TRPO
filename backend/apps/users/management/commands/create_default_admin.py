from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()

DEFAULT_EMAIL = "admin@admin.com"
DEFAULT_PASSWORD = "admin"
DEFAULT_FIRST_NAME = "Admin"


class Command(BaseCommand):
    help = "Создаёт администратора по умолчанию, если ни одного пользователя нет."

    def handle(self, *args, **options):
        if User.objects.exists():
            self.stdout.write("Пользователи уже существуют, пропускаем создание администратора.")
            return

        User.objects.create_user(
            email=DEFAULT_EMAIL,
            password=DEFAULT_PASSWORD,
            first_name=DEFAULT_FIRST_NAME,
            role=User.Role.ADMIN,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Администратор создан: {DEFAULT_EMAIL} / {DEFAULT_PASSWORD}"
            )
        )
