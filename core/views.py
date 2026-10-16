from django.shortcuts import render

from courses.models import Category, Course


def home(request):
    featured_courses = Course.objects.filter(is_published=True)[:6]
    context = {
        'featured_courses': featured_courses,
        'categories': Category.choices,
    }
    return render(request, 'core/home.html', context)
