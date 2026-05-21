from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import Business, Client


class CustomJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user_type = validated_token.get('type')

        if user_type == 'business':
            business_id = validated_token.get('business_id')
            try:
                return Business.objects.get(id=business_id)
            except Business.DoesNotExist:
                return None

        elif user_type == 'client':
            client_id = validated_token.get('client_id')
            try:
                return Client.objects.get(id=client_id)
            except Client.DoesNotExist:
                return None

        return None