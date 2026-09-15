from django.conf import settings
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.http import HttpRequest
from django.utils import timezone

# Лимит попыток входа для одного IP (защита от перебора паролей).
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300


def _client_ip(request: HttpRequest) -> str:
    # Доверенный источник IP — заголовок X-Real-IP, который nginx всегда
    # перезаписывает значением $remote_addr (см. nginx.conf: proxy_set_header
    # X-Real-IP $remote_addr). Пока эта перезапись работает, клиент не может
    # подделать свой IP. X-Forwarded-For сознательно НЕ используется — его
    # клиент подделывает напрямую. Если nginx перестанет перезаписывать
    # X-Real-IP (например, из-за смены конфига — важно не сломать это),
    # запасной вариант: REMOTE_ADDR от обратного прокси.
    real = request.META.get('HTTP_X_REAL_IP', '')
    if real:
        return real.strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def _attempts_key(ip: str) -> str:
    return f'login_failures:{ip}'


class RateLimitedLoginView(LoginView):
    """Вход с ограничением числа неудачных попыток по IP."""

    def form_valid(self, form):
        cache.delete(_attempts_key(_client_ip(self.request)))
        return super().form_valid(form)

    def form_invalid(self, form):
        ip = _client_ip(self.request)
        failures = 0

        cached = cache.get(_attempts_key(ip))
        if cached:
            count, first_at = cached
            if (timezone.now() - first_at).total_seconds() <= LOGIN_WINDOW_SECONDS:
                failures = count
            else:
                failures = 0

        failures += 1
        if failures >= LOGIN_MAX_ATTEMPTS:
            cache.set(_attempts_key(ip), (failures, timezone.now()), LOGIN_WINDOW_SECONDS)
            form.add_error(None, 'Слишком много неудачных попыток. Попробуйте через 5 минут.')
        else:
            cache.set(_attempts_key(ip), (failures, timezone.now()), LOGIN_WINDOW_SECONDS)

        return super().form_invalid(form)
