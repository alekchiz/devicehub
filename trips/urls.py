from django.urls import path
from . import views

urlpatterns = [
    path('', views.trips_list, name='trips_list'),
    path('create/', views.trip_create, name='trip_create'),
    path('<int:pk>/delete/', views.trip_delete, name='trip_delete'),
    path('export/', views.export_trips_excel, name='export_trips'),
]
