from django.urls import path

from . import views

app_name = 'speaking'

urlpatterns = [
    path('<int:part>/', views.part, name='part'),
    path('<int:part>/sets/<int:set_pk>/', views.ready, name='ready'),
]
