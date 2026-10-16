from django.http import Http404
from django.shortcuts import get_object_or_404

from .models import Course


def visible_course(request, **lookup):
    """The course, or a 404 when it is still a draft and the visitor is not an admin."""
    course = get_object_or_404(Course, **lookup)
    if not course.is_published and not (request.user.is_authenticated and request.user.is_admin):
        raise Http404
    return course
