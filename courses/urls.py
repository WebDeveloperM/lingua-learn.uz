from django.urls import path

from . import views

app_name = 'courses'

EXERCISE = '<slug:slug>/part/<int:part_number>/exercise/<int:exercise_number>/'

urlpatterns = [
    path('', views.course_list, name='course_list'),
    path('audio/<int:pk>/', views.exercise_audio, name='exercise_audio'),
    path('image/<int:pk>/', views.exercise_image, name='exercise_image'),
    path('<slug:slug>/', views.course_detail, name='course_detail'),
    path('<slug:slug>/enroll/', views.enroll, name='enroll'),
    path(EXERCISE, views.exercise_intro, name='exercise_intro'),
    path(EXERCISE + 'play/', views.exercise_play, name='exercise_play'),
    path(EXERCISE + 'submit/', views.exercise_submit, name='exercise_submit'),
]
