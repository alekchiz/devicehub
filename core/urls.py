from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from accounts.views import RateLimitedLoginView

def redirect_to_dashboard(request):
    return redirect('dashboard')

urlpatterns = [
    path('', redirect_to_dashboard, name='home'),
    path('admin/', admin.site.urls),
    path('accounts/login/', RateLimitedLoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/accounts/login/'), name='logout'),
    path('dashboard/', include('devices.urls')),
    path('tickets/', include('tickets.urls')),
    path('shipments/', include('shipments.urls')),
    path('trips/', include('trips.urls')),
]
