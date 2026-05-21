from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password, check_password
from django.utils.text import slugify
from uuid import uuid4
from datetime import datetime, timedelta
from django.utils import timezone
from uuid import uuid4

class Business(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='business')

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    description = models.TextField(blank=True)

    location = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)
    response_time = models.CharField(
        max_length=100,
        blank=True,
        default="Usually responds in 24h"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            while Business.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

class Service(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    duration = models.IntegerField()  # в минутах
    duration_unit = models.CharField(max_length=10, default='min')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='USD')
    category = models.CharField(max_length=100, blank=True)
    date = models.DateField(default="2026-04-20")
    is_booked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Обратная совместимость
    @property
    def duration_minutes(self):
        return self.duration


class Slot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='slots')
    date = models.DateField()
    time_start = models.TimeField()
    time_end = models.TimeField()
    is_booked = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('business', 'date', 'time_start')
    
    def get_datetime(self):
        return timezone.make_aware(datetime.combine(self.date, self.time_start))
    
    @property
    def time(self):
        """Для совместимости с frontend"""
        return self.time_start.strftime('%H:%M')


class Client(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True, null=True, blank=True)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    
    is_verified = models.BooleanField(default=False)
    verification_code = models.CharField(max_length=6, null=True, blank=True)
    verification_expires = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def generate_code(self):
        import random
        self.verification_code = str(random.randint(100000, 999999))
        self.verification_expires = timezone.now() + timedelta(minutes=10)
        self.save()
        return self.verification_code
    
    def is_code_valid(self, code):
        if self.verification_code != code:
            return False
        if timezone.now() > self.verification_expires:
            return False
        return True
    
    def verify(self):
        self.is_verified = True
        self.verification_code = None
        self.verification_expires = None
        self.save()


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Ожидание'),
        ('confirmed', 'Подтверждено'),
        ('cancelled', 'Отменено'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    service = models.ForeignKey('Service', on_delete=models.CASCADE, related_name='bookings')
    organization = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='all_bookings')
    
    client_name = models.CharField(max_length=255)
    client_email = models.EmailField()
    client_phone = models.CharField(max_length=20, blank=True)
    
    date = models.DateField(null=True, blank=True) 
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Автоматически берем дату из связанного сервиса, если она не задана вручную
        if not self.date and self.service:
            self.date = self.service.date
        
        # Автоматически подтягиваем организацию из сервиса
        if not self.organization and self.service:
            self.organization = self.service.business
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.client_name} - {self.service.name} ({self.date})"

    class Meta:
        ordering = ['-created_at']


class Reminder(models.Model):
    CHANNEL_CHOICES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='reminders')
    scheduled_time = models.DateTimeField()
    sent = models.BooleanField(default=False)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Напоминание для {self.booking.id} через {self.channel}"