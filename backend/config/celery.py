import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('multichat')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'update-manager-statuses': {
        'task': 'apps.chats.tasks.update_manager_statuses',
        'schedule': 60.0,  # каждые 60 секунд
    },
}
