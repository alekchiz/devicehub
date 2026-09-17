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
# В Docker кеш живёт в Redis (сервис redis в compose), можно переопределить через .env.
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/1')
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://redis:6379/0')
# Собираем статику из исходников (static/) и отдаём собранную (staticfiles/),
# а не сырую из исходной директории, чтобы не зависеть от host-mount.
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'
