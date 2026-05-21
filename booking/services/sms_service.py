import requests
from django.conf import settings


class SMSCService:
    API_URL = 'https://smsc.ru/sys/send.php'
    
    @classmethod
    def send_sms(cls, phone, message):
        phone = ''.join(filter(str.isdigit, phone))
        if phone.startswith('8') and len(phone) == 11:
            phone = '7' + phone[1:]
        
        params = {
            'login': settings.SMSC_LOGIN,
            'psw': settings.SMSC_PASSWORD,
            'phones': phone,
            'mes': message,
            'sender': settings.SMSC_SENDER,
            'fmt': 3,
            'charset': 'utf-8',
        }
        
        try:
            response = requests.get(cls.API_URL, params=params, timeout=10)
            return response.json()
        except Exception as e:
            print(f'SMS sending failed: {e}')
            return None
    
    @classmethod
    def send_verification_code(cls, phone, code):
        message = f'Код подтверждения: {code}. Действителен 10 минут.'
        return cls.send_sms(phone, message)
    
    @classmethod
    def send_reminder(cls, phone, booking):
        message = f'Напоминание: {booking.slot.date.strftime("%d.%m")} в {booking.slot.time_start.strftime("%H:%M")} - {booking.business.name}'
        return cls.send_sms(phone, message)