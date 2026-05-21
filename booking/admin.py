from django.contrib import admin
from .models import (
    Business,
    Service,
    Client,
    Booking,
    Reminder
)

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_email', 'created_at')

    def get_email(self, obj):
        return obj.user.email

    get_email.short_description = 'Email'

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'business', 'duration', 'price', 'created_at')
    search_fields = ('name',)
    list_filter = ('business',)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'is_verified')
    search_fields = ('name', 'email', 'phone')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'client_name', 'service', 'organization', 'status', 'date')
    
    list_filter = ('status', 'organization', 'date')
    
    search_fields = ('client_name', 'client_email', 'service')


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ('booking', 'scheduled_time', 'channel', 'sent')
    list_filter = ('channel', 'sent')