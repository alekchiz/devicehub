from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('status/', views.device_status_feed, name='device_status_feed'),
    path('clients/', views.clients_list, name='clients_list'),
    path('history/', views.device_history, name='device_history'),
    path('reports/', views.reports_page, name='reports'),
    path('analytics/', views.analytics_uptime, name='analytics'),
    path('import/', views.import_exams, name='import_exams'),
    path('bulk-action/', views.bulk_action, name='bulk_action'),
    path('device/<int:pk>/', views.device_detail_modal, name='device_detail_modal'),
    path('device/<int:pk>/detail/', views.device_detail_page, name='device_detail_page'),
    path('device/<int:pk>/reboot/', views.device_reboot, name='device_reboot'),
    path('device/<int:pk>/stop/', views.device_stop, name='device_stop'),
    path('device/<int:pk>/start/', views.device_start, name='device_start'),
    path('device/<int:pk>/upload/', views.device_upload, name='device_upload'),
    path('device/<int:pk>/set-password/', views.device_set_password, name='device_set_password'),
    path('device/<int:pk>/report/', views.export_device_report, name='export_device_report'),
    path('export/', views.export_devices_excel, name='export_devices'),
    path('export/history/', views.export_devices_history, name='export_devices_history'),
    path('export/stats/', views.export_devices_stats, name='export_devices_stats'),
    path('export/repairs-report/', views.export_repairs_report, name='export_repairs_report'),
    path('export/alco-report/', views.export_alco_report, name='export_alco_report'),
    path('export/tonometer-report/', views.export_tonometer_report, name='export_tonometer_report'),
    
    path('repairs/', views.repairs_list, name='repairs_list'),
    path('repairs/create/', views.repair_create, name='repair_create'),
    path('repairs/<int:pk>/start/', views.repair_start, name='repair_start'),
    path('repairs/<int:pk>/ready/', views.repair_ready, name='repair_ready'),
    path('repairs/export/', views.export_repairs_excel, name='export_repairs'),
    
    path('verifications/', views.verifications_list, name='verifications_list'),
    path('verifications/create/', views.verification_create, name='verification_create'),
    path('verifications/<int:pk>/verify/', views.verification_verify, name='verification_verify'),
    path('verifications/export/', views.export_verifications_excel, name='export_verifications'),
    path('verifications/export/med-devices/', views.export_med_devices_report, name='export_med_devices'),
]
