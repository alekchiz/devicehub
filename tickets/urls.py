from django.urls import path
from . import views

urlpatterns = [
    path('', views.tickets_list, name='tickets_list'),
    path('create/', views.ticket_create, name='ticket_create'),
    path('<int:pk>/edit/', views.ticket_edit, name='ticket_edit'),
    path('<int:pk>/assign/', views.ticket_assign, name='ticket_assign'),
    path('<int:pk>/status/', views.ticket_change_status, name='ticket_change_status'),
    path('<int:pk>/comment/', views.ticket_comment, name='ticket_comment'),
    path('export/', views.export_tickets_excel, name='export_tickets'),
    path('logs/', views.activity_log_list, name='activity_logs'),
]
