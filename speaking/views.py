from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from courses.access import visible_course
from courses.models import Category

from .models import (
    DEFAULT_QUESTIONS, SCORING, SpeakingPart, SpeakingPractice, SpeakingSet, minutes_label, part_info, questions_label,
)


def _speaking_course(request, slug):
    course = visible_course(request, slug=slug)
    if course.category != Category.SPEAKING:
        raise Http404
    return course


def _part(number):
    try:
        return SpeakingPart(number)
    except ValueError:
        raise Http404


def _ready_sets(course):
    """The sets a student can practise: the ones that have at least one question."""
    return SpeakingSet.objects.filter(course=course).annotate(question_total=Count('questions')).filter(
        question_total__gt=0)


def _practised(user, course):
    if not user.is_authenticated:
        return set()
    return set(SpeakingPractice.objects.filter(user=user, set__course=course).values_list('set_id', flat=True))


def speaking_hub(request, course):
    """The Speaking practice page: how answers are scored and the four parts (the course page itself)."""
    sets = list(_ready_sets(course))
    practised = _practised(request.user, course)
    parts = []
    for part in SpeakingPart:
        part_sets = [speaking_set for speaking_set in sets if speaking_set.part == part]
        size = max((speaking_set.question_total for speaking_set in part_sets), default=DEFAULT_QUESTIONS)
        parts.append({
            **part_info(part, size),
            'sets_total': len(part_sets),
            'practised': sum(1 for speaking_set in part_sets if speaking_set.pk in practised),
        })
    return render(request, 'speaking/hub.html', {
        'course': course,
        'parts': parts,
        'scoring': [{'percent': percent, 'icon': icon, 'name': name} for percent, icon, name in SCORING],
    })


def part(request, slug, part):
    """One part: its sets of practice questions, each with a button to practise it."""
    course = _speaking_course(request, slug)
    part = _part(part)
    practised = _practised(request.user, course)
    sets = list(_ready_sets(course).filter(part=part).prefetch_related('questions'))
    for speaking_set in sets:
        speaking_set.question_list = list(speaking_set.questions.all())
        speaking_set.is_practised = speaking_set.pk in practised
    return render(request, 'speaking/part.html', {
        'course': course,
        'part': part_info(part),
        'sets': sets,
    })


@login_required
def ready(request, slug, part, set_pk):
    """"Ready?": what the practice of one set will be like, before it starts."""
    course = _speaking_course(request, slug)
    part = _part(part)
    speaking_set = get_object_or_404(
        SpeakingSet.objects.prefetch_related('questions'), pk=set_pk, course=course, part=part)
    count = len(speaking_set.questions.all())
    if not count:
        raise Http404
    return render(request, 'speaking/ready.html', {
        'course': course,
        'part': part_info(part),
        'set': speaking_set,
        'questions': questions_label(count),
        'duration': minutes_label(part, count),
        'coins': count,
    })
