from itertools import groupby

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from courses.access import visible_course
from courses.models import Category

from . import guides
from .models import WritingAnswer, WritingSubmission, WritingTest, count_words

MAX_TEXT_LENGTH = 8000


def writing_hub(request, course):
    """The Writing practice page: every test of the course, month by month (the course page itself)."""
    tests = list(course.writing_tests.all())
    sent = set()
    if request.user.is_authenticated:
        sent = set(
            WritingSubmission.objects.filter(user=request.user, test__course=course).values_list('test_id', flat=True)
        )
    for test in tests:
        test.is_sent = test.pk in sent
    months = [
        {'month': first_day, 'tests': list(items)}
        for first_day, items in groupby(tests, key=lambda test: test.date.replace(day=1))
    ]
    return render(request, 'writing/hub.html', {'course': course, 'tests': tests, 'months': months})


def _writing_course(request, slug):
    course = visible_course(request, slug=slug)
    if course.category != Category.WRITING:
        raise Http404
    return course


def _get_test(request, slug, pk):
    course = _writing_course(request, slug)
    return course, get_object_or_404(WritingTest, pk=pk, course=course)


def _clean_seconds(raw, limit):
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        return None
    return max(0, min(seconds, limit))


def guide(request, slug):
    course = _writing_course(request, slug)
    return render(request, 'writing/guide.html', {'course': course, 'groups': guides.INFORMAL_EMAIL})


@login_required
def intro(request, slug, pk):
    course, test = _get_test(request, slug, pk)
    return render(request, 'writing/intro.html', {
        'course': course,
        'test': test,
        'tasks': list(test.tasks.exclude(instruction='')),
    })


@login_required
def write(request, slug, pk):
    course, test = _get_test(request, slug, pk)
    tasks = list(test.tasks.exclude(instruction=''))
    if not tasks:
        return redirect('writing:intro', slug=slug, pk=pk)
    seconds = test.duration_minutes * 60
    return render(request, 'writing/write.html', {
        'course': course,
        'test': test,
        'tasks': tasks,
        'duration_seconds': seconds,
        'timer_label': f'{seconds // 60:02d}:{seconds % 60:02d}',
    })


@login_required
@require_POST
def send(request, slug, pk):
    course, test = _get_test(request, slug, pk)
    tasks = list(test.tasks.exclude(instruction=''))
    if not tasks:
        raise Http404

    texts = {
        task.slot: (request.POST.get(f'answer_{task.slot}') or '').strip()[:MAX_TEXT_LENGTH] for task in tasks
    }
    if not any(texts.values()):
        messages.info(request, 'Nothing was sent: you did not write anything.')
        return redirect('writing:intro', slug=slug, pk=pk)

    submission = WritingSubmission.objects.create(
        test=test, user=request.user,
        seconds_used=_clean_seconds(request.POST.get('time_used'), test.duration_minutes * 60),
    )
    WritingAnswer.objects.bulk_create([
        WritingAnswer(submission=submission, slot=slot, text=text, word_count=count_words(text))
        for slot, text in texts.items()
    ])
    return redirect('writing:sent', slug=slug, submission_pk=submission.pk)


@login_required
def sent(request, slug, submission_pk):
    course = _writing_course(request, slug)
    submission = get_object_or_404(
        WritingSubmission.objects.select_related('test', 'user'), pk=submission_pk, test__course=course,
    )
    if submission.user_id != request.user.pk and not request.user.is_admin:
        raise Http404
    return render(request, 'writing/sent.html', {
        'course': course,
        'test': submission.test,
        'submission': submission,
        'answers': list(submission.answers.all()),
    })
