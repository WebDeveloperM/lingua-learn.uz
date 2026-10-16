from django.urls import path

from . import practice_views, speaking_views, views, writing_views

app_name = 'panel'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    path('students/', views.student_list, name='student_list'),
    path('students/<int:pk>/', views.student_detail, name='student_detail'),
    path('students/<int:pk>/toggle-active/', views.student_toggle_active, name='student_toggle_active'),
    path('students/<int:pk>/delete/', views.student_delete, name='student_delete'),
    path('enrollments/<int:pk>/progress/', views.enrollment_progress, name='enrollment_progress'),

    path('rating/', views.rating, name='rating'),

    path('courses/', views.course_list, name='course_list'),
    path('courses/new/', views.course_create, name='course_create'),
    path('courses/<int:pk>/edit/', views.course_edit, name='course_edit'),
    path('courses/<int:pk>/toggle-published/', views.course_toggle_published, name='course_toggle_published'),
    path('courses/<int:pk>/delete/', views.course_delete, name='course_delete'),

    path('courses/<int:course_pk>/parts/new/', practice_views.part_create, name='part_create'),
    path('parts/<int:pk>/', practice_views.part_edit, name='part_edit'),
    path('parts/<int:pk>/delete/', practice_views.part_delete, name='part_delete'),
    path('parts/<int:pk>/exercises/add/', practice_views.exercise_add, name='exercise_add'),
    path('exercises/<int:pk>/edit/', practice_views.exercise_edit, name='exercise_edit'),
    path('exercises/<int:pk>/delete/', practice_views.exercise_delete, name='exercise_delete'),

    path('courses/<int:course_pk>/writing/new/', writing_views.writing_test_create, name='writing_test_create'),
    path('courses/<int:course_pk>/writing/submissions/', writing_views.writing_submissions, name='writing_submissions'),
    path('writing/<int:pk>/', writing_views.writing_test_edit, name='writing_test_edit'),
    path('writing/<int:pk>/delete/', writing_views.writing_test_delete, name='writing_test_delete'),
    path('writing/submissions/<int:pk>/', writing_views.writing_submission, name='writing_submission'),

    path('courses/<int:course_pk>/speaking/<int:part>/', speaking_views.speaking_part, name='speaking_part'),
]
