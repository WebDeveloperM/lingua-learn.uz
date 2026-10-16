from django.urls import path

from . import views

app_name = 'writing'

urlpatterns = [
    path('guide/', views.guide, name='guide'),
    path('sent/<int:submission_pk>/', views.sent, name='sent'),
    path('<int:pk>/', views.intro, name='intro'),
    path('<int:pk>/write/', views.write, name='write'),
    path('<int:pk>/send/', views.send, name='send'),
]
