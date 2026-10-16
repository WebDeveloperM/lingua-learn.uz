from django.urls import path

from . import views

app_name = 'speaking'

urlpatterns = [
    path('<int:part>/', views.part, name='part'),
    path('<int:part>/sets/<int:set_pk>/', views.ready, name='ready'),
    path('<int:part>/sets/<int:set_pk>/finish/', views.finish, name='finish'),
    path('results/<int:attempt_pk>/', views.result, name='result'),
    path('results/<int:attempt_pk>/feedback/', views.retry_feedback, name='retry_feedback'),
    path('answers/<int:answer_pk>/audio/', views.answer_audio, name='answer_audio'),
]
