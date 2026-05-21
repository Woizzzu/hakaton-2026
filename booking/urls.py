from django.urls import path
from . import views

urlpatterns = [
    # 1. AUTHENTICATION 
    path('auth/register/', views.auth_register, name='auth-register'),
    path('auth/login/', views.auth_login, name='auth-login'),
    path('auth/refresh/', views.auth_refresh, name='auth-refresh'),
    path('auth/logout/', views.auth_logout, name='auth-logout'),
    path('auth/me/', views.auth_me, name='auth-me'),

    # 2. ORGANIZATIONS (Public & Management) 
    path('organizations/', views.organizations_list, name='organizations-list'),
    path('organizations/<uuid:id>/', views.organizations_detail, name='organizations-detail'),
    
   

    # 3. SERVICES (Public)
    path('services/', views.services_list, name='services-list'),
    path('services/<uuid:pk>/', views.services_detail, name='services-detail'),
    path('services/<uuid:pk>/availability/', views.services_availability, name='services-availability'),
    
    # 4. BOOKINGS 
    path('bookings/', views.bookings_list_create, name='bookings-list-create'),
    path('bookings/calendar/', views.bookings_calendar, name='bookings-calendar'),
    path('bookings/<uuid:pk>/status/', views.update_booking_status, name='booking-update-status'),
    path('bookings/<uuid:pk>/', views.delete_booking, name='booking-delete'),
    
    # 5. ORGANIZATION MANAGEMENT (Protected) 
    path('organizations/me/', views.organizations_me_update, name='organizations-me-update'),
    path('organizations/me/services/', views.services_create, name='services-create'),
    path('organizations/me/services/<uuid:pk>/', views.services_update, name='services-update'),
    path('organizations/me/services/<uuid:pk>/delete/', views.services_delete, name='services-delete'),
    
    # 6. DASHBOARD & SLOTS 
    path('dashboard/stats/', views.dashboard_stats, name='dashboard-stats'),
    path('me/slots/', views.my_slots, name='my-slots'),
    path('me/slots/<uuid:slot_id>/', views.delete_slot, name='delete-slot'),
    
    # 7. CLIENT & LEGACY
    path('clients/register/', views.client_register, name='client-register'),
    path('clients/verify/', views.client_verify, name='client-verify'),
    path('me/bookings/', views.my_bookings, name='my-bookings'), # Брони самого клиента
    path('me/business/', views.update_business, name='update-business'),
]