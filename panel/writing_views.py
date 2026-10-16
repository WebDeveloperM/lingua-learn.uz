from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from courses.models import Category, Course
from writing.models import WritingSubmission, WritingTest

from .decorators import admin_required
from .writing_forms import WritingTestForm

SUBMISSIONS_PER_PAGE = 20


def _writing_course(pk):
    return get_object_or_404(Course, pk=pk, category=Category.WRITING)


def _test_form_view(request, course, test=None):
    instance = test or WritingTest(course=course)
    if request.method == 'POST':
        form = WritingTestForm(request.POST, instance=instance)
        if form.is_valid():
            saved = form.save()
            messages.success(request, f'"{saved.title}" testi saqlandi.')
            return redirect('panel:writing_test_edit', pk=saved.pk)
    else:
        initial = {} if test else {'date': date.today(), 'shift': 1, 'duration_minutes': 60}
        form = WritingTestForm(instance=instance, initial=initial)

    return render(request, 'panel/writing_test_form.html', {
        'form': form,
        'course': course,
        'test': test,
        'sections': form.task_sections(),
        'student_url': reverse('writing:intro', args=[course.slug, test.pk]) if test else '',
    })


@admin_required
def writing_test_create(request, course_pk):
    return _test_form_view(request, _writing_course(course_pk))


@admin_required
def writing_test_edit(request, pk):
    test = get_object_or_404(WritingTest.objects.select_related('course'), pk=pk)
    return _test_form_view(request, test.course, test)


@admin_required
@require_POST
def writing_test_delete(request, pk):
    test = get_object_or_404(WritingTest.objects.select_related('course'), pk=pk)
    course = test.course
    title = test.title
    test.delete()
    messages.success(request, f'"{title}" testi o\'chirildi.')
    return redirect('panel:course_edit', pk=course.pk)


@admin_required
def writing_submissions(request, course_pk):
    course = _writing_course(course_pk)
    queryset = (
        WritingSubmission.objects.filter(test__course=course)
        .select_related('user', 'test')
        .prefetch_related('answers')
    )
    page = Paginator(queryset, SUBMISSIONS_PER_PAGE).get_page(request.GET.get('page'))
    return render(request, 'panel/writing_submissions.html', {'course': course, 'page_obj': page})


@admin_required
def writing_submission(request, pk):
    submission = get_object_or_404(
        WritingSubmission.objects.select_related('user', 'test__course').prefetch_related('answers', 'test__tasks'),
        pk=pk,
    )
    tasks = {task.slot: task for task in submission.test.tasks.all()}
    rows = [{'answer': answer, 'task': tasks.get(answer.slot)} for answer in submission.answers.all()]
    return render(request, 'panel/writing_submission.html', {
        'submission': submission, 'course': submission.test.course, 'rows': rows,
    })
