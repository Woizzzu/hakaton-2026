import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'booking_api.settings')

app = Celery('booking_api')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'send-reminders-every-5-min': {
        'task': 'booking.tasks.send_reminders_task',
        'schedule': 300.0,
    },
}