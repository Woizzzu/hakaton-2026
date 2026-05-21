import os
import sys

BASE_DIR = '/home/m/mybusin2ru/public_html'
VENV_SITE_PACKAGES = '/home/m/mybusin2ru/public_html/venv/lib/python3.11/site-packages'

sys.path.insert(0, BASE_DIR)
sys.path.insert(0, VENV_SITE_PACKAGES)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'booking_api.settings')

# Активируем venv
import site
site.addsitedir(VENV_SITE_PACKAGES)

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()