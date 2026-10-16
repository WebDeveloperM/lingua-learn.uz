from django.contrib import messages
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from courses.models import Category, Course
from speaking.models import SpeakingPart, SpeakingSet, part_info, set_name

from .decorators import admin_required
from .speaking_forms import SetFormSet, questions_text, save_sets


def speaking_part_rows(course):
    """The four parts of a Speaking course with how many sets and questions each already has (course edit page)."""
    sets = SpeakingSet.objects.filter(course=course).annotate(question_total=Count('questions'))
    rows = []
    for part in SpeakingPart:
        part_sets = [speaking_set for speaking_set in sets if speaking_set.part == part]
        rows.append({
            **part_info(part),
            'sets_count': len(part_sets),
            'questions_count': sum(speaking_set.question_total for speaking_set in part_sets),
        })
    return rows


def _set_id(form):
    try:
        return int(form['set_id'].value())
    except (TypeError, ValueError):
        return None


@admin_required
def speaking_part(request, course_pk, part):
    course = get_object_or_404(Course, pk=course_pk, category=Category.SPEAKING)
    try:
        part = SpeakingPart(part)
    except ValueError:
        raise Http404

    sets = list(SpeakingSet.objects.filter(course=course, part=part).prefetch_related('questions'))
    if request.method == 'POST':
        formset = SetFormSet(request.POST, prefix='sets')
        if formset.is_valid():
            save_sets(course, part, formset)
            messages.success(request, f'{part.label}: setlar saqlandi.')
            return redirect('panel:speaking_part', course_pk=course.pk, part=part.value)
    else:
        formset = SetFormSet(
            prefix='sets',
            initial=[{'set_id': speaking_set.pk, 'questions': questions_text(speaking_set)} for speaking_set in sets],
        )

    titles = {speaking_set.pk: speaking_set.title for speaking_set in sets}
    for form in formset:
        form.set_title = titles.get(_set_id(form))
    next_number = max((speaking_set.number for speaking_set in sets), default=0) + 1
    return render(request, 'panel/speaking_part.html', {
        'course': course,
        'part': part_info(part),
        'formset': formset,
        'next_title': set_name(next_number),
        'student_url': reverse('speaking:part', args=[course.slug, part.value]),
    })
