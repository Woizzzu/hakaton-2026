from rest_framework import serializers
from .models import Business, Service, Client, Booking, Slot

# Базовый сериализатор для обёртки 

class SuccessResponseSerializer(serializers.Serializer):
    """Базовый для всех ответов в формате frontend"""
    success = serializers.BooleanField(default=True)
    data = serializers.DictField(required=False)
    message = serializers.CharField(required=False, allow_blank=True)
    
    @staticmethod
    def wrap(data, success=True, message=""):
        return {
            "success": success,
            "data": data,
            "message": message
        }


# Business 

class BusinessListSerializer(serializers.ModelSerializer):
    """Для списка организаций (GET /api/organizations)"""
    servicesCount = serializers.IntegerField(source='services.count', read_only=True)
    rating = serializers.DecimalField(max_digits=2, decimal_places=1, default=4.8)
    reviewCount = serializers.IntegerField(default=0)
    
    class Meta:
        model = Business
        fields = ['id', 'name', 'description', 'slug', 'servicesCount', 'rating', 'reviewCount']

class ServiceSerializer(serializers.ModelSerializer):
    business = serializers.ReadOnlyField(source='business.id')

    class Meta:
        model = Service
        fields = [
            'id', 
            'name', 
            'description', 
            'duration', 
            'duration_unit', 
            'price', 
            'currency',
            'business',
	    'date',
            'is_booked' 
        ]


class BusinessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = ['id', 'name', 'slug']


class ServiceDetailSerializer(ServiceSerializer):
    availableSlots = serializers.SerializerMethodField()

    class Meta(ServiceSerializer.Meta):
        fields = ServiceSerializer.Meta.fields + ['availableSlots']

    def get_availableSlots(self, obj):
        if not hasattr(obj, 'business') or not obj.business:
            return []
        
        slots = obj.business.slots.filter(is_booked=False).order_by('date', 'time_start')
        result = {}

        for slot in slots:
            date_str = str(slot.date)
            if date_str not in result:
                result[date_str] = []
            result[date_str].append(slot.time_start.strftime('%H:%M'))

        return [{"date": date, "times": times} for date, times in result.items()]

class BusinessDetailSerializer(serializers.ModelSerializer):
    services = ServiceSerializer(many=True, read_only=True)

    class Meta:
        model = Business
        fields = [
            'id',
            'name',
            'description',
            'slug',
            'location',
            'contact_email',
            'response_time',
            'services'
        ]

class BusinessCreateSerializer(serializers.Serializer):
    organizationName = serializers.CharField(source='name', max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    confirmPassword = serializers.CharField(write_only=True)
    
    def validate(self, data):
        if data.get('password') != data.get('confirmPassword'):
            raise serializers.ValidationError("Passwords don't match")
        return data


class BusinessPatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = ['name', 'description']


# Service 

class ServiceWithOrganizationSerializer(ServiceSerializer):
    class Meta(ServiceSerializer.Meta):
        fields = list(ServiceSerializer.Meta.fields) + ['date']



class ServiceAvailabilitySerializer(serializers.ModelSerializer):
    serviceId = serializers.UUIDField(source='id')
    availability = serializers.SerializerMethodField()
    
    class Meta:
        model = Service
        fields = [
            'id', 
            'name', 
            'description', 
            'price', 
            'currency', 
            'duration', 
            'date',       
            'business', 
            'business_name'
        ]
    
    def get_availability(self, obj):
        if not hasattr(obj, 'business') or not obj.business:
            return []

        slots_qs = obj.business.slots.filter(is_booked=False).order_by('date', 'time_start')
        res_map = {}
        
        for slot in slots_qs:
            d_str = str(slot.date)
            if d_str not in res_map:
                res_map[d_str] = []
            res_map[d_str].append({
                "time": slot.time_start.strftime('%H:%M'),
                "available": not slot.is_booked
            })
        
        return [{"date": d, "slots": s} for d, s in res_map.items()]


class ServiceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = [
            'name', 
            'description', 
            'duration', 
            'duration_unit', 
            'price', 
            'currency', 
            'date'
        ]


# Client 

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'name', 'email', 'phone']


class ClientRegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    email = serializers.EmailField(required=False, allow_null=True)
    phone = serializers.CharField(max_length=20, required=False, allow_null=True)


# Booking 

class BookingListSerializer(serializers.ModelSerializer):
    serviceId = serializers.UUIDField(source='service.id', read_only=True)
    serviceName = serializers.CharField(source='service.name', read_only=True)
    organizationId = serializers.UUIDField(source='business.id', read_only=True)
    organizationName = serializers.CharField(source='business.name', read_only=True)
    clientName = serializers.CharField(source='client_name', read_only=True)
    clientEmail = serializers.CharField(source='client_email', read_only=True)
    date = serializers.DateField(format='%Y-%m-%d', read_only=True)
    time = serializers.CharField(source='slot.time_start', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', format='%Y-%m-%dT%H:%M:%SZ')
    
    class Meta:
        model = Booking
        fields = ['id', 'serviceId', 'serviceName', 'organizationId', 'organizationName',
                  'clientName', 'clientEmail', 'date', 'time', 'status', 'createdAt']


class BookingDetailSerializer(serializers.ModelSerializer):
    service = ServiceSerializer(read_only=True)
    organization = BusinessListSerializer(source='business', read_only=True)
    client = serializers.SerializerMethodField()
    date = serializers.CharField(source='slot.date', read_only=True)
    time = serializers.CharField(source='slot.time_start', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', format='%Y-%m-%dT%H:%M:%SZ')
    confirmedAt = serializers.DateTimeField(source='confirmed_at', format='%Y-%m-%dT%H:%M:%SZ', allow_null=True)
    
    class Meta:
        model = Booking
        fields = ['id', 'service', 'organization', 'client', 'date', 'time', 
                  'status', 'notes', 'createdAt', 'confirmedAt']
    
    def get_client(self, obj):
        return {
            'name': obj.client_name,
            'email': obj.client_email,
            'phone': obj.client_phone
        }


class BookingCreateSerializer(serializers.Serializer):
    serviceId = serializers.UUIDField()
    organizationId = serializers.UUIDField()
    date = serializers.DateField()
    time = serializers.CharField()
    clientName = serializers.CharField(max_length=255)
    clientEmail = serializers.EmailField()
    clientPhone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class BookingCalendarSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    bookingsByDate = serializers.DictField()


class BookingSerializer(serializers.ModelSerializer):
    serviceId = serializers.ReadOnlyField(source='service.id')
    serviceName = serializers.ReadOnlyField(source='service.name') 
    organizationId = serializers.ReadOnlyField(source='organization.id')
    clientName = serializers.ReadOnlyField(source='client_name')
    clientEmail = serializers.ReadOnlyField(source='client_email')
    createdAt = serializers.ReadOnlyField(source='created_at')
    
    date = serializers.DateField(format="%Y-%m-%d") 

    class Meta:
        model = Booking
        fields = [
            'id', 'serviceId', 'serviceName', 'clientName', 
            'clientEmail', 'date', 'status', 'organizationId', 'createdAt'
        ]


# Auth 

class TokensSerializer(serializers.Serializer):
    accessToken = serializers.CharField(source='access')
    refreshToken = serializers.CharField(source='refresh')


class UserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()

class SlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Slot
        fields = ['id', 'date', 'time_start', 'time_end', 'is_booked']
class BusinessPatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = ['name', 'description']