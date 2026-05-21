from django.contrib.auth.hashers import check_password
from .serializers import ServiceWithOrganizationSerializer
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from datetime import datetime, timedelta
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .utils import success_response, error_response
from .models import Business, Service, Slot, Client, Booking
from .serializers import LoginSerializer
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from .serializers import (
    BusinessCreateSerializer,
    BusinessSerializer,
    ServiceSerializer,
    BookingSerializer,
    BusinessPatchSerializer,
)
from .services.email_service import EmailService
from .services.sms_service import SMSCService
from .tasks import create_reminders_for_booking


# Утилита для обёртки ответов 

def success_response(data=None, message="", status_code=200):
    return Response({
        "success": True,
        "data": data,
        "message": message
    }, status=status_code)

def error_response(message, status_code=400, error_code="ERROR"):
    return Response({
        "success": False,
        "data": None,
        "message": message,
        "error": {
            "code": error_code,
            "details": {}
        }
    }, status=status_code)

def get_business_from_user(user):
    """Получает Business из User (через related_name или filter)"""
    if hasattr(user, 'business'):
        return user.business
    from .models import Business
    return Business.objects.filter(user=user).first()


# 1. AUTHENTICATION

from django.contrib.auth.models import User

@api_view(['POST'])
@permission_classes([AllowAny])
def auth_register(request):
    serializer = BusinessCreateSerializer(data=request.data)

    if not serializer.is_valid():
        return error_response(serializer.errors, 400, "VALIDATION_ERROR")

    data = serializer.validated_data
    email = data['email']
    password = data['password']
    name = data['name']

    # проверка User
    if User.objects.filter(username=email).exists():
        return error_response("User already exists", 409, "CONFLICT")

    # создаем пользователя
    user = User.objects.create_user(
    username=data['email'],
    email=data['email'],
    password=data['password']
)

    business = Business.objects.create(
    user=user,
    name=data['name'],
    contact_email=data['email'],
    description=data.get('description', '')
)

    # JWT
    refresh = RefreshToken.for_user(user)
    refresh['business_id'] = str(business.id)
    refresh['type'] = 'business'

    return success_response({
        "user": {
            "id": user.id,
            "email": user.email,
        },
        "organization": {
            "id": str(business.id),
            "name": business.name,
            "description": business.description,
            "slug": business.slug
        },
        "tokens": {
            "accessToken": str(refresh.access_token),
            "refreshToken": str(refresh)
        }
    }, status_code=201)

@api_view(['POST'])
@permission_classes([AllowAny])
def auth_login(request):
    serializer = LoginSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(serializer.errors, 400, "VALIDATION_ERROR")
    
    data = serializer.validated_data
    try:
        # 1. Ищем пользователя по email (username)
        user = User.objects.get(username=data['email'])
    except User.DoesNotExist:
        return error_response("Неверный email или пароль", 401, "UNAUTHORIZED")

    # 2. Проверяем пароль
    if not user.check_password(data['password']):
        return error_response("Неверный email или пароль", 401, "UNAUTHORIZED")

    # 3. Находим связанный бизнес
    try:
        business = Business.objects.get(user=user)
    except Business.DoesNotExist:
        return error_response("Профиль организации не найден", 404, "NOT_FOUND")

    # 4. ГЕНЕРИРУЕМ ТОКЕН
    refresh = RefreshToken.for_user(user)
    
    # Добавляем кастомные поля 
    refresh['business_id'] = str(business.id)
    refresh['email'] = business.contact_email
    refresh['type'] = 'business'

    return success_response({
        "user": {
            "id": user.id,
            "email": business.contact_email,
            "name": business.name
        },
        "tokens": {
            "accessToken": str(refresh.access_token),
            "refreshToken": str(refresh)
        }
    })


@api_view(['POST'])
def auth_refresh(request):
    """POST /api/auth/refresh - Обновление токена"""
    refresh_token = request.data.get('refresh')
    if not refresh_token:
        return error_response("Refresh token required", 400, "VALIDATION_ERROR")
    
    try:
        refresh = RefreshToken(refresh_token)
        new_access = str(refresh.access_token)
        new_refresh = str(refresh)
        
        return success_response({
            "accessToken": new_access,
            "refreshToken": new_refresh
        })
    except Exception:
        return error_response("Invalid refresh token", 401, "AUTH_ERROR")


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def auth_logout(request):
    try:
        refresh_token = request.data.get("refreshToken")

        if not refresh_token:
            return error_response("Refresh token required", 400, "VALIDATION_ERROR")

        token = RefreshToken(refresh_token)
        token.blacklist()

        return success_response({"message": "Logged out successfully"})

    except Exception as e:
        return error_response(str(e), 400, "LOGOUT_FAILED")


@api_view(['GET'])
@permission_classes([IsAuthenticated])  # ← ДОБАВИТЬ
def auth_me(request):
    """GET /auth/me - Текущий пользователь"""
    # request.user это User, получаем Business
    business = getattr(request.user, 'business', None)
    
    if not business:
        return error_response("Business not found", 404, "NOT_FOUND")
    
    user_data = {
        "id": str(business.id),
        "email": business.contact_email,
        "name": business.name
    }
    
    org_data = {
        "id": str(business.id),
        "name": business.name,
        "description": business.description,
        "slug": business.slug
    }
    
    return success_response({
        "user": user_data,
        "organization": org_data
    })

# 2. ORGANIZATIONS (Public)

@api_view(['GET', 'PATCH']) 
@permission_classes([AllowAny]) 
def organizations_list(request):
    """
    GET   /api/organizations - Список всех организаций (публично)
    PATCH /api/organizations - Обновление своей организации (по токену)
    """
    
    # ОБРАБОТКА PATCH
    if request.method == 'PATCH':
        # 1. Проверяем авторизацию
        if not request.user.is_authenticated:
            return error_response("Необходима авторизация", 401)
        
        # 2. Находим организацию текущего пользователя
        business = Business.objects.filter(user=request.user).first()
        if not business:
            return error_response("Организация не найдена для этого пользователя", 404)
        
        # 3. Частичное обновление через BusinessPatchSerializer
        serializer = BusinessPatchSerializer(business, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return success_response(serializer.data, message="Данные организации успешно обновлены")
        
        return error_response(serializer.errors, 400)

    # ОБРАБОТКА GET
    businesses = Business.objects.all().order_by('name')
    
    # Поиск 
    search = request.query_params.get('search')
    if search:
        businesses = businesses.filter(name__icontains=search)
    
    # Инициализация пагинатора
    paginator = PageNumberPagination()
    # Устанавливаем размер страницы
    try:
        paginator.page_size = int(request.query_params.get('limit', 20))
    except ValueError:
        paginator.page_size = 20

    # Пагинация QuerySet
    businesses_page = paginator.paginate_queryset(businesses, request)
    
    # Сериализация
    from .serializers import BusinessSerializer 
    serializer = BusinessSerializer(businesses_page, many=True)
    
    return success_response({
        "items": serializer.data,
        "pagination": {
            "total": paginator.page.paginator.count,
            "totalPages": paginator.page.paginator.num_pages,
            "current_page": paginator.page.number,
            "limit": paginator.page_size,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link()
        }
    })

    #ОБРАБОТКА GET (СПИСОК)
    businesses = Business.objects.all()
    
    # Поиск
    search = request.query_params.get('search')
    if search:
        businesses = businesses.filter(name__icontains=search)
    
    # Пагинация
    try:
        page = int(request.query_params.get('page', 1))
        limit = int(request.query_params.get('limit', 20))
    except ValueError:
        page, limit = 1, 20

    start = (page - 1) * limit
    end = start + limit
    total = businesses.count()
    
    businesses_page = businesses.order_by('name')[start:end] # Добавили сортировку для стабильности
    serializer = BusinessListSerializer(businesses_page, many=True)
    
    return success_response({
        "items": serializer.data,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": (total + limit - 1) // limit
        }
    })


@api_view(['GET', 'PATCH'])
@permission_classes([AllowAny])
def organizations_detail(request, id):
    try:
        business = Business.objects.get(id=id)
    except Business.DoesNotExist:
        return error_response("Not found", 404)

    if request.method == 'PATCH':
        #только владелец может менять
        if not request.user.is_authenticated or business.user != request.user:
            return error_response("У вас нет прав для редактирования этой организации", 403)
        
        # Передаем данные в сериализатор
        serializer = BusinessPatchSerializer(business, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save() # <-- Вот эта строка записывает изменения в базу
            return success_response(serializer.data, message="Данные обновлены")
        
        return error_response(serializer.errors, 400)
    

    
    serializer = BusinessSerializer(business)
    return success_response(serializer.data)



@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def organization_patch(request):
    """
    PATCH /api/organizations/
    Обновление имени и описания организации на основе токена
    """
    # 1. Находим организацию
    business = Business.objects.filter(user=request.user).first()
    
    if not business:
        return error_response("Организация не найдена для данного пользователя", 404)

    # 2. Передаем данные в сериализатор
    serializer = BusinessPatchSerializer(business, data=request.data, partial=True)
    
    if serializer.is_valid():
        serializer.save()
        # Возвращаем
        return success_response(serializer.data, message="Данные организации успешно обновлены")
    
    return error_response(serializer.errors, 400)





# 3. SERVICES (Public) 

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def services_list(request):
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return error_response("Authentication required", 401)
        return _services_create_logic(request)

    # Логика GET с поиском 
    services = Service.objects.filter(is_booked=False).select_related('business').order_by('-id')

    # ПОИСК
    search_query = request.query_params.get('search', None)
    if search_query:
        services = services.filter(name__icontains=search_query)
    
    # Пагинация
    paginator = PageNumberPagination()
    try:
        limit = int(request.query_params.get('limit', 10))
        paginator.page_size = limit
    except ValueError:
        paginator.page_size = 10 
    
    services_page = paginator.paginate_queryset(services, request)
    serializer = ServiceWithOrganizationSerializer(services_page, many=True)
    
    return success_response({
        "items": serializer.data,
        "pagination": {
            "count": paginator.page.paginator.count,
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "total_pages": paginator.page.paginator.num_pages,
            "current_page": paginator.page.number
        }
    })


def _services_create_logic(request):
    """Внутренняя логика создания услуги"""
    try:
        # Пытаемся найти организацию текущего пользователя
        business = Business.objects.filter(user=request.user).first()
        
        if not business:
            return error_response("Organization not found for this user", 404, "NOT_FOUND")

        data = request.data
        
        # Валидация обязательных полей
        if not data.get('name') or not data.get('date'):
            return error_response("Name and Date are required", 400, "VALIDATION_ERROR")

        with transaction.atomic():
            service = Service.objects.create(
                business=business,
                name=data.get('name'),
                description=data.get('description', ''),
                duration=data.get('duration', 60),
                duration_unit=data.get('duration_unit', 'min'),
                price=data.get('price', 0),
                currency=data.get('currency', 'RUB'), # Исправил на RUB по умолчанию
                date=data.get('date'),
                category=data.get('category', '')
            )

        serializer = ServiceSerializer(service)
        return success_response(serializer.data, status_code=201)
        
    except Exception as e:
        return error_response(f"Server error: {str(e)}", 500, "INTERNAL_ERROR")


@api_view(['GET'])
@permission_classes([AllowAny])
def services_detail(request, pk):
    """GET /api/services/:id - Детали услуги"""
    try:
        service = Service.objects.get(pk=pk)
    except Service.DoesNotExist:
        return error_response("Service not found", 404, "NOT_FOUND")
    
    serializer = ServiceSerializer(service)
    return success_response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def services_availability(request, pk):
    """GET /api/services/:id/availability - Доступные слоты"""
    try:
        service = Service.objects.get(pk=pk)
    except Service.DoesNotExist:
        return error_response("Service not found", 404, "NOT_FOUND")
    
    # Фильтр по датам
    start_date = request.query_params.get('startDate')
    end_date = request.query_params.get('endDate')
    
    slots = service.business.slots.filter(is_booked=False)
    if start_date:
        slots = slots.filter(date__gte=start_date)
    if end_date:
        slots = slots.filter(date__lte=end_date)
    
    # Группировка по датам
    availability = {}
    for slot in slots.order_by('date', 'time_start'):
        date_str = str(slot.date)
        if date_str not in availability:
            availability[date_str] = []
        availability[date_str].append({
            "time": slot.time_start.strftime('%H:%M'),
            "available": not slot.is_booked
        })
    
    result = [{"date": date, "slots": slots} for date, slots in availability.items()]
    
    return success_response({
        "serviceId": str(service.id),
        "availability": result
    })


# 4. BOOKINGS (Protected) 

# 1. логика создания
def _create_booking_logic(request):
    """Внутренняя логика создания бронирования (POST)"""
    data = request.data
    service_id = data.get('service_id')
    
    # 1. Базовая проверка обязательных полей
    if not all([service_id, data.get('client_name'), data.get('client_email')]):
        return error_response("Missing required fields", 400, "VALIDATION_ERROR")

    try:
        service = Service.objects.select_related('business').get(id=service_id)
    except (Service.DoesNotExist, Exception):
        return error_response("Service not found", 404, "NOT_FOUND")

    if service.is_booked:
        return error_response("Service already booked", 400, "ALREADY_BOOKED")

    try:
        with transaction.atomic():
            booking = Booking.objects.create(
                service=service,
                client_name=data.get('client_name'),
                client_email=data.get('client_email'),
                client_phone=data.get('client_phone', ''),
                date=service.date,
                organization=service.business,
                status='pending'
            )
            service.is_booked = True
            service.save()

        
        serializer = BookingSerializer(booking)
        return success_response(serializer.data, 201)

    except Exception as e:
        return error_response(f"Booking failed: {str(e)}", 500)

def _get_bookings_list_logic(request):
    #Внутренняя логика получения списка для владельца (GET)
    # Находим организацию текущего авторизованного пользователя
    business = Business.objects.filter(user=request.user).first()
    if not business:
        return error_response("Organization not found for current user", 404)

    # Оптимизируем запрос через select_related
    bookings = Booking.objects.filter(organization=business).select_related('service').order_by('-created_at')
    
    # Фильтр по статусу
    status_filter = request.query_params.get('status')
    if status_filter:
        bookings = bookings.filter(status=status_filter)

    serializer = BookingSerializer(bookings, many=True)
    return success_response(serializer.data)

def _get_bookings_list_logic(request):
    #Внутренняя логика получения списка (GET)
    # Находим организацию владельца из токена
    business = Business.objects.filter(user=request.user).first()
    if not business:
        return error_response("Organization not found", 404)

    bookings = Booking.objects.filter(organization=business).order_by('-created_at')
    
    # Фильтр по статусу
    status_filter = request.query_params.get('status')
    if status_filter:
        bookings = bookings.filter(status=status_filter)

    serializer = BookingSerializer(bookings, many=True)
    return success_response(serializer.data)

@api_view(['GET', 'POST'])
@permission_classes([AllowAny]) # Разрешаем вход
def bookings_list_create(request):
    #Главная точка входа для /api/bookings/
    if request.method == 'POST':
        return _create_booking_logic(request)
    
    elif request.method == 'GET':
        # проверяем токен
        if not request.user.is_authenticated:
            return error_response("Authentication required", 401)
        return _get_bookings_list_logic(request)




@api_view(['POST'])
def bookings_create(request):
    #POST /api/bookings - Создание бронирования
    serializer = BookingCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", 400, "VALIDATION_ERROR")
    
    data = serializer.validated_data
    
    # Проверка бизнеса и услуги
    try:
        business = Business.objects.get(id=data['organizationId'])
        service = Service.objects.get(id=data['serviceId'], business=business)
    except (Business.DoesNotExist, Service.DoesNotExist):
        return error_response("Service or organization not found", 404, "NOT_FOUND")
    
    # Поиск слота
    try:
        time_obj = datetime.strptime(data['time'], '%H:%M').time()
        slot = Slot.objects.select_for_update().get(
            business=business,
            date=data['date'],
            time_start=time_obj,
            is_booked=False
        )
    except Slot.DoesNotExist:
        return error_response("Slot not available", 409, "CONFLICT")
    
    # Создание или получение клиента
    client, _ = Client.objects.get_or_create(
        contact_email=data['clientEmail'],
        defaults={'name': data['clientName'], 'phone': data.get('clientPhone', '')}
    )
    
    with transaction.atomic():
        slot.is_booked = True
        slot.save()
        
        booking = Booking.objects.create(
            client=client,
            business=business,
            service=service,
            slot=slot,
            client_name=data['clientName'],
            client_contact_email=data['clientEmail'],
            client_phone=data.get('clientPhone', ''),
            notes=data.get('notes', ''),
            status='pending'
        )
        
        create_reminders_for_booking.delay(booking.id)
    
    serializer = BookingListSerializer(booking)
    return success_response(serializer.data, status_code=201)








@api_view(['GET'])
def bookings_calendar(request):
    business = get_business_from_user(request.user)
    if not business:
        return error_response("Not authenticated", 401, "AUTH_ERROR")

    year = int(request.query_params.get('year', timezone.now().year))
    month = int(request.query_params.get('month', timezone.now().month))

    bookings = Booking.objects.filter(
        business=business,
        slot__date__year=year,
        slot__date__month=month
    ).select_related('slot')

    bookings_by_date = {}
    for booking in bookings:
        day = booking.slot.date.day
        bookings_by_date.setdefault(day, []).append({
            "id": str(booking.id),
            "time": booking.slot.time_start.strftime('%H:%M'),
            "status": booking.status,
            "clientName": booking.client_name
        })

    return success_response({
        "year": year,
        "month": month,
        "bookingsByDate": bookings_by_date
    })

@api_view(['GET'])
def bookings_detail(request, pk):
    """GET /api/bookings/:id - Детали бронирования"""
    business = get_business_from_user(request.user)
    client_id = request.auth.get('client_id') if request.auth else None

    try:
        if business:
            booking = Booking.objects.get(pk=pk, business=business)
        elif client_id:
            booking = Booking.objects.get(pk=pk, client_id=client_id)
        else:
            return error_response("Not authenticated", 401, "AUTH_ERROR")

    except Booking.DoesNotExist:
        return error_response("Booking not found", 404, "NOT_FOUND")

    serializer = BookingDetailSerializer(booking)
    return success_response(serializer.data)
@api_view(['PATCH'])
def bookings_confirm(request, pk):
    """PATCH /api/bookings/:id/confirm - Подтверждение бронирования"""
    business = get_business_from_user(request.user)
    if not business:
        return error_response("Not authenticated", 401, "AUTH_ERROR")

    bookings = Booking.objects.filter(business=business)
    
    try:
        booking = Booking.objects.get(pk=pk, business=business)
    except Booking.DoesNotExist:
        return error_response("Booking not found", 404, "NOT_FOUND")
    
    booking.confirm()
    
    return success_response({
        "id": str(booking.id),
        "status": booking.status,
        "confirmedAt": booking.confirmed_at.strftime('%Y-%m-%dT%H:%M:%SZ') if booking.confirmed_at else None
    })


@api_view(['PATCH'])
def bookings_cancel(request, pk):
    """PATCH /api/bookings/:id/cancel - Отмена бронирования"""
    business = get_business_from_user(request.user)
    client_id = request.auth.get('client_id') if request.auth else None
    
    try:
        if business:
            booking = Booking.objects.get(pk=pk, business=business)
        elif client_id:
            booking = Booking.objects.get(pk=pk, client_id=client_id)
        else:
            return error_response("Not authenticated", 401, "AUTH_ERROR")
    except Booking.DoesNotExist:
        return error_response("Booking not found", 404, "NOT_FOUND")
    
    reason = request.data.get('reason', '')
    
    try:
        booking.cancel(reason)
    except ValueError as e:
        return error_response(str(e), 400, "VALIDATION_ERROR")
    
    return success_response({
        "id": str(booking.id),
        "status": booking.status,
        "cancelledAt": booking.cancelled_at.strftime('%Y-%m-%dT%H:%M:%SZ') if booking.cancelled_at else None,
        "reason": reason
    })




@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_booking(request, pk):
   
    # 1. Найти Booking
    try:
        booking = Booking.objects.get(pk=pk)
    except (Booking.DoesNotExist, ValidationError):
        return error_response("Бронирование не найдено", 404)

    # 2. Проверить права владельца
    if booking.organization.user != request.user:
        return error_response("У вас нет прав для удаления этого бронирования", 403)

    # Используем транзакцию
    with transaction.atomic():
        # 3-4. Найти связанный Service и освободить его
        service = booking.service
        service.is_booked = False
        service.save()

        # 5. Удалить Booking
        booking.delete()

    return success_response({"success": True}, status_code=204)



# 5. ORGANIZATION MANAGEMENT (Protected) 

@api_view(['PATCH'])
def organizations_me_update(request):
    business = get_business_from_user(request.user)
    if not business:
        return error_response("Not authenticated", 401, "AUTH_ERROR")

    if 'name' in request.data:
        business.name = request.data['name']
        business.slug = slugify(request.data['name'])

    if 'description' in request.data:
        business.description = request.data['description']

    if 'location' in request.data:
        business.location = request.data['location']

    if 'contactEmail' in request.data:
        business.contact_email = request.data['contactEmail']

    if 'responseTime' in request.data:
        business.response_time = request.data['responseTime']

    business.save()

    return success_response({
        "id": str(business.id),
        "name": business.name,
        "description": business.description,
        "slug": business.slug,
        "location": business.location,
        "contactEmail": business.contact_email,
        "responseTime": business.response_time,
        "updatedAt": business.updated_at.strftime('%Y-%m-%dT%H:%M:%SZ')
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def services_create(request):
    # 1. Берем business_id напрямую из payload токена (SimpleJWT хранит его там)
    # Если в токене нет business_id, ищем по пользователю
    business_id = request.auth.get('business_id')
    
    try:
        if business_id:
            business = Business.objects.get(id=business_id)
        else:
            business = Business.objects.get(user=request.user)
    except Business.DoesNotExist:
        return error_response("Organization not found", 404, "NOT_FOUND")

    data = request.data

    # 2. Создаем сервис
    try:
        service = Service.objects.create(
            business=business,
            name=data.get('name'),
            description=data.get('description', ''),
            duration=data.get('duration', 60),
            duration_unit=data.get('duration_unit', 'min'), 
            price=data.get('price', 0),
            currency=data.get('currency', 'USD'),
            date=data.get('date'), 
            category=data.get('category', '')
        )
    except Exception as e:
        return error_response(f"Ошибка при создании: {str(e)}", 400)

    # 3. Возвращаем результат
    serializer = ServiceSerializer(service)
    return success_response(serializer.data, status_code=201)

@api_view(['PATCH'])
def services_update(request, pk):
    business = get_business_from_user(request.user)
    if not business:
        return error_response("Not authenticated", 401, "AUTH_ERROR")

    try:
        service = Service.objects.get(pk=pk, business=business)
    except Service.DoesNotExist:
        return error_response("Service not found", 404, "NOT_FOUND")

    for field in ['name', 'description', 'duration', 'price']:
        if field in request.data:
            setattr(service, field, request.data[field])

    service.save()

    serializer = ServiceSerializer(service)
    return success_response(serializer.data)


@api_view(['DELETE'])
def services_delete(request, pk):
    business = get_business_from_user(request.user)
    if not business:
        return error_response("Not authenticated", 401, "AUTH_ERROR")

    try:
        service = Service.objects.get(pk=pk, business=business)
    except Service.DoesNotExist:
        return error_response("Service not found", 404, "NOT_FOUND")

    service.delete()
    return success_response(None, "Service deleted")


# 6. DASHBOARD

@api_view(['GET'])
def dashboard_stats(request):
    """GET /api/dashboard/stats - Статистика для дашборда"""
    business = get_business_from_user(request.user)
    if not business:
        return error_response("Not authenticated", 401, "AUTH_ERROR")
    
    now = timezone.now()
    
    # Подсчёты
    total_bookings = Booking.objects.filter(business=business).count()
    active_bookings = Booking.objects.filter(
        business_id=business_id,
        status='pending'
    ).count()
    confirmed_bookings = Booking.objects.filter(
        business_id=business_id,
        status='confirmed'
    ).count()
    total_services = Service.objects.filter(business_id=business_id).count()
    
    # Популярные услуги 
    popular_services = []
    
    return success_response({
        "activeBookings": active_bookings,
        "confirmedBookings": confirmed_bookings,
        "totalBookings": total_bookings,
        "totalServices": total_services,
        "revenueThisMonth": 0,  
        "revenueLastMonth": 0,  
        "popularServices": popular_services
    })


# Старые endpoints 

@api_view(['GET'])
@permission_classes([AllowAny])
def public_slots(request):
    """GET /api/slots - Старый endpoint"""
    business_id = request.query_params.get('business_id')
    date = request.query_params.get('date')
    
    if not business:
        return error_response("business_id required", 400, "VALIDATION_ERROR")
    
    slots = Slot.objects.filter(business_id=business_id, is_booked=False)
    if date:
        slots = slots.filter(date=date)
    
    serializer = SlotSerializer(slots, many=True)
    return success_response(serializer.data)


@api_view(['GET'])
@permission_classes([AllowAny])
def available_dates(request):
    """GET /api/slots/available-dates - Старый endpoint"""
    business_id = request.query_params.get('business_id')
    if not business:
        return error_response("business_id required", 400, "VALIDATION_ERROR")
    
    dates = Slot.objects.filter(
        business_id=business_id, 
        is_booked=False
    ).values_list('date', flat=True).distinct()
    
    return success_response([str(d) for d in dates])


# Client endpoints 

@api_view(['POST'])
@permission_classes([AllowAny])
def client_register(request):
    """POST /api/clients/register"""
    serializer = ClientRegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response("Validation error", 400, "VALIDATION_ERROR")
    
    data = serializer.validated_data
    if not data.get('phone') and not data.get('email'):
        return error_response("Phone or email required", 400, "VALIDATION_ERROR")
    
    if data.get('phone'):
        client, _ = Client.objects.get_or_create(
            phone=data['phone'],
            defaults={'name': data['name'], 'email': data.get('email')}
        )
    else:
        client, _ = Client.objects.get_or_create(
            contact_email=data['email'],
            defaults={'name': data['name']}
        )
    
    code = client.generate_code()
    
    if client.phone:
        SMSCService.send_verification_code(client.phone, code)
    if client.email:
        EmailService.send_verification_code(client.email, code)
    
    return success_response({
        "client_id": str(client.id),
        "message": "Verification code sent"
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def client_verify(request):
    """POST /api/clients/verify"""
    client_id = request.data.get('client_id')
    code = request.data.get('code')
    
    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return error_response("Client not found", 404, "NOT_FOUND")
    
    if not client.is_code_valid(code):
        return error_response("Invalid or expired code", 400, "VALIDATION_ERROR")
    
    client.verify()
    
    refresh = RefreshToken()
    refresh['client_id'] = str(client.id)
    refresh['type'] = 'client'
    
    return success_response({
        "accessToken": str(refresh.access_token),
        "refreshToken": str(refresh),
        "client": {
            "id": str(client.id),
            "name": client.name,
            "email": client.email,
            "phone": client.phone
        }
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def client_resend_code(request):
    """POST /api/clients/resend-code"""
    client_id = request.data.get('client_id')
    
    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return error_response("Client not found", 404, "NOT_FOUND")
    
    code = client.generate_code()
    
    if client.phone:
        SMSCService.send_verification_code(client.phone, code)
    if client.email:
        EmailService.send_verification_code(client.email, code)
    
    return success_response({"message": "Code resent"})


@api_view(['GET'])
def my_bookings(request):
    """GET /api/me/bookings - Бронирования клиента"""
    client_id = request.auth.get('client_id') if request.auth else None
    if not client_id:
        return error_response("Not authenticated", 401, "AUTH_ERROR")
    
    bookings = Booking.objects.filter(client_id=client_id).order_by('-created_at')
    serializer = BookingListSerializer(bookings, many=True)
    
    return success_response(serializer.data)


@api_view(['GET', 'POST'])
def my_slots(request):
    """GET/POST /api/me/slots - Управление слотами бизнеса"""
    business = get_business_from_user(request.user)
    if not business:
        return error_response("Not authenticated", 401, "AUTH_ERROR")
    
    if request.method == 'GET':
        date = request.query_params.get('date')
        slots = Slot.objects.filter(business=business)
        if date:
            slots = slots.filter(date=date)
        serializer = SlotSerializer(slots, many=True)
        return success_response(serializer.data)
    
    # POST
    data = request.data
    try:
        slot = Slot.objects.create(
    business=business,
    date=data['date'],
    time_start=data['time_start'],
    time_end=data['time_end']
)
        serializer = SlotSerializer(slot)
        return success_response(serializer.data, status_code=201)
    except Exception as e:
        return error_response(str(e), 400, "VALIDATION_ERROR")


@api_view(['DELETE'])
def delete_slot(request, slot_id):
    """DELETE /api/me/slots/:id"""
    business = get_business_from_user(request.user)
    if not business:
        return error_response("Not authenticated", 401, "AUTH_ERROR")
    
    try:
        slot = Slot.objects.get(id=slot_id, business=business)
    except Slot.DoesNotExist:
        return error_response("Slot not found", 404, "NOT_FOUND")
    
    if slot.is_booked:
        return error_response("Cannot delete booked slot", 409, "CONFLICT")
    
    slot.delete()
    return success_response({"message": "Slot deleted"})


@api_view(['GET'])
def my_bookings_business(request):
    """GET /api/me/bookings - Бронирования бизнеса (устаревший)"""
    return bookings_list(request)



@permission_classes([IsAuthenticated])
def update_booking_status(request, pk):
   
    # 1. Найти Booking по id (pk)
    try:
        booking = Booking.objects.get(pk=pk)
    except (Booking.DoesNotExist, ValidationError):
        return error_response("Бронирование не найдено", 404)

    # 2. Проверить что владелец организации — это текущий пользователь
    if booking.organization.user != request.user:
        return error_response("У вас нет прав для управления этим бронированием", 403)

    new_status = request.data.get('status')
    if new_status not in ['confirmed', 'cancelled']:
        return error_response("Недопустимый статус. Используйте 'confirmed' или 'cancelled'", 400)

    # Используем транзакцию для атомарности изменений
    with transaction.atomic():
        booking.status = new_status
        booking.save()

        # 4. Если status == "cancelled"
        if new_status == "cancelled":
            service = booking.service
            service.is_booked = False
            service.save()

    return success_response({
        "id": str(booking.id),
        "status": booking.status,
        "updated_at": booking.updated_at.strftime('%Y-%m-%dT%H:%M:%SZ')
    })


@api_view(['PATCH'])
def update_business(request):
    """PATCH /api/me/business (устаревший)"""
    return organizations_me_update(request)