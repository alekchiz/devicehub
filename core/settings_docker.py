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
# В Docker статику раздаёт nginx напрямую из смонтированного каталога, поэтому
# не используем STATICFILES_DIRS (иначе будет конфликт с STATIC_ROOT).
STATICFILES_DIRS = []
STATIC_ROOT = '/app/static'
STATIC_URL = '/static/'
