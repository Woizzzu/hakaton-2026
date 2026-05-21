from django.core.mail import EmailMultiAlternatives
from django.conf import settings


class Yandex360Service:
    @classmethod
    def send_email(cls, to_email, subject, text_content, html_content=None):
        try:
            if html_content:
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=text_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[to_email]
                )
                msg.attach_alternative(html_content, "text/html")
                msg.send()
            else:
                from django.core.mail import send_mail
                send_mail(
                    subject=subject,
                    message=text_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[to_email],
                    fail_silently=False,
                )
            return True
        except Exception as e:
            print(f'Email failed: {e}')
            return False
    
    @classmethod
    def send_verification_code(cls, email, code):
        subject = 'Код подтверждения записи'
        text = f'Ваш код подтверждения: {code}\nКод действителен 10 минут.'
        html = f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 500px; margin: 0 auto; background: white; 
                     border-radius: 10px; padding: 30px; }}
        .code-box {{ background: #ffcc00; padding: 20px; border-radius: 8px; 
                    text-align: center; margin: 20px 0; }}
        .code {{ font-size: 32px; font-weight: bold; letter-spacing: 5px; margin: 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h2>🔐 Подтверждение записи</h2>
        <p>Ваш код подтверждения:</p>
        <div class="code-box">
            <p class="code">{code}</p>
        </div>
        <p>Код действителен в течение <strong>10 минут</strong>.</p>
    </div>
</body>
</html>
'''
        return cls.send_email(email, subject, text, html)
    
    @classmethod
    def send_reminder(cls, email, booking):
        subject = '⏰ Напоминание о вашей записи'
        text = f'''Здравствуйте, {booking.client.name}!

Напоминаем о записи:
📅 {booking.slot.date.strftime('%d.%m.%Y')} в {booking.slot.time_start.strftime('%H:%M')}
🏢 {booking.business.name}

Ждём вас!'''
        
        html = f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 550px; margin: 0 auto; background: white; 
                     border-radius: 10px; overflow: hidden; }}
        .header {{ background: #ffcc00; padding: 20px; text-align: center; }}
        .content {{ padding: 30px; }}
        .info-box {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>⏰ Напоминание о записи</h2>
        </div>
        <div class="content">
            <p>Здравствуйте, <strong>{booking.client.name}</strong>!</p>
            <div class="info-box">
                <p>📅 <strong>Дата:</strong> {booking.slot.date.strftime('%d.%m.%Y')}</p>
                <p>⏰ <strong>Время:</strong> {booking.slot.time_start.strftime('%H:%M')}</p>
                <p>🏢 <strong>Организация:</strong> {booking.business.name}</p>
                <p>🛠 <strong>Услуга:</strong> {booking.service.name if booking.service else 'Не указана'}</p>
            </div>
        </div>
    </div>
</body>
</html>
'''
        return cls.send_email(email, subject, text, html)


EmailService = Yandex360Service