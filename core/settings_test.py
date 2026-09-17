"""Настройки для тестов: лёгкая SQLite in-memory, без внешних сервисов."""
from .settings import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Для тестов используем изолированный кэш в памяти (таблица django_cache не нужна).
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'device-hub-test-cache',
    }
}

# Не кешируем агрегаты дашборда в тестах — кеш живёт между тестами и
# «протухшие» счётчики ломали бы проверки.
STATS_CACHE_TTL = 0

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Тестовый Django-клиент ходит по http: выключаем secure-cookie/HSTS из прода,
# иначе сессия не «липнет» при login/force_login.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
