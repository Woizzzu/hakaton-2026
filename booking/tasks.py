from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from .models import Reminder, Booking
from .services.email_service import EmailService
from .services.sms_service import SMSCService


@shared_task
def send_reminders_task():
    now = timezone.now()
    reminders = Reminder.objects.filter(sent=False, scheduled_time__lte=now)
    
    for reminder in reminders:
        booking = reminder.booking
        client = booking.client
        
        if reminder.channel == 'email' and client.email:
            EmailService.send_reminder(client.email, booking)
        elif reminder.channel == 'sms' and client.phone:
            message = f'Напоминание: {booking.slot.date} в {booking.slot.time_start}'
            SMSCService.send_sms(client.phone, message)
        
        reminder.sent = True
        reminder.save()
    
    return f'Sent {reminders.count()} reminders'


@shared_task
def create_reminders_for_booking(booking_id):
    try:
        booking = Booking.objects.get(id=booking_id)
    except Booking.DoesNotExist:
        return
    
    slot_datetime = booking.slot.get_datetime()
    
    reminder_24h = slot_datetime - timedelta(hours=24)
    if reminder_24h > timezone.now():
        if booking.client.email:
            Reminder.objects.create(booking=booking, scheduled_time=reminder_24h, channel='email')
        if booking.client.phone:
            Reminder.objects.create(booking=booking, scheduled_time=reminder_24h, channel='sms')
    
    reminder_2h = slot_datetime - timedelta(hours=2)
    if reminder_2h > timezone.now():
        if booking.client.email:
            Reminder.objects.create(booking=booking, scheduled_time=reminder_2h, channel='email')
        if booking.client.phone:
            Reminder.objects.create(booking=booking, scheduled_time=reminder_2h, channel='sms')