from django.urls import path
from . import views

urlpatterns = [
    path('', views.shipments_list, name='shipments_list'),
    path('create/', views.shipment_create, name='shipment_create'),
    path('<int:pk>/status/', views.shipment_change_status, name='shipment_change_status'),
    path('export/', views.export_shipments_excel, name='export_shipments'),
]
