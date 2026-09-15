from .settings import *
import os

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'device_hub'),
        'USER': os.getenv('DB_USER', 'devicehub'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'securepassword'),
        'HOST': os.getenv('DB_HOST', 'db'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

DEBUG = os.getenv('DJANGO_DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'support-pak.ru,www.support-pak.ru').split(',')
# Собираем статику из исходников (static/) и отдаём собранную (staticfiles/),
# а не сырую из исходной директории, чтобы не зависеть от host-mount.
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'
