from django.contrib import admin
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.utils.translation import gettext as _

from accounts.views import RateLimitedLoginView

admin.site.site_header = 'МедКиоск — администрирование'
admin.site.site_title = 'МедКиоск'
admin.site.index_title = 'Разделы'


def _admin_login(request, extra_context=None):
    """Логин админки с тем же rate-limit по IP, что и у /accounts/login/."""
    if request.method == 'GET' and admin.site.has_permission(request):
        # Уже залогиненный администратор идёт сразу в разделы.
        return HttpResponseRedirect(reverse('admin:index', current_app=admin.site.name))

    return RateLimitedLoginView.as_view(
        extra_context={
            **admin.site.each_context(request),
            'title': _('Log in'),
            'subtitle': None,
            'app_path': request.get_full_path(),
            'username': request.user.get_username(),
        },
        redirect_authenticated_user=True,
        success_url=reverse('admin:index'),
        authentication_form=admin.site.login_form,
    )(request)


admin.site.login = _admin_login
