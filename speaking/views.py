import os
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from courses.access import visible_course
from courses.models import Category
from courses.streaming import file_response_with_range

from . import ai
from .feedback import analyse_attempt
from .models import (
    AUDIO_EXTENSIONS, DEFAULT_QUESTIONS, MAX_TRANSCRIPT_LENGTH, PART_RULES, SCORING, SpeakingAnswer, SpeakingAttempt,
    SpeakingPart, SpeakingPractice, SpeakingSet, minutes_label, part_info, questions_label,
)

MAX_ATTEMPTS_PER_HOUR = 30  # every attempt asks the AI for feedback, so a student cannot run them without limit
MAX_AUDIO_BYTES = 5 * 1024 * 1024


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


def _own_or_admin(request, attempt):
    if attempt.user_id != request.user.pk and not request.user.is_admin:
        raise Http404


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
    size = max((len(speaking_set.question_list) for speaking_set in sets), default=DEFAULT_QUESTIONS)
    return render(request, 'speaking/part.html', {
        'course': course,
        'part': part_info(part, size),
        'sets': sets,
    })


def _get_set(course, part, set_pk):
    return get_object_or_404(SpeakingSet.objects.prefetch_related('questions'), pk=set_pk, course=course, part=part)


def _secure_address(request):
    """The https address of this very page when the visitor needs it for the microphone, otherwise "".

    Browsers give the microphone only to https pages and to localhost. A visitor of the plain-http address of the site
    (http://192.168.2.72:8000/...) is therefore pointed to the same page on the https port (settings.HTTPS_PORT)."""
    port = settings.HTTPS_PORT
    if not port.isdigit() or request.is_secure():
        return ''
    host = urlsplit(f'//{request.get_host()}').hostname or ''
    if not host or host == 'localhost' or host.endswith('.localhost') or host in ('127.0.0.1', '::1'):
        return ''
    netloc = f'[{host}]' if ':' in host else host
    if port != '443':
        netloc = f'{netloc}:{port}'
    return f'https://{netloc}{request.get_full_path()}'


@login_required
def ready(request, slug, part, set_pk):
    """"Ready?": what the practice of one set will be like. The practice itself runs on this page once Start is
    pressed, so the browser keeps the permission to talk and to use the microphone."""
    course = _speaking_course(request, slug)
    part = _part(part)
    speaking_set = _get_set(course, part, set_pk)
    questions = list(speaking_set.questions.all())
    if not questions:
        raise Http404
    session = PART_RULES[part]['session']
    config = None
    if session:
        config = {
            'part': part.label,
            'think': session['think'],
            'talk': session['talk'],
            'questions': [{'id': question.pk, 'text': question.text} for question in questions],
            'finishUrl': reverse('speaking:finish', args=[course.slug, part.value, speaking_set.pk]),
            'backUrl': reverse('speaking:part', args=[course.slug, part.value]),
        }
    return render(request, 'speaking/ready.html', {
        'course': course,
        'part': part_info(part),
        'set': speaking_set,
        'questions': questions_label(len(questions)),
        'duration': minutes_label(part, len(questions)),
        'coins': len(questions),
        'session': config,
        'secure_url': _secure_address(request) if config else '',
        # the server turns the recordings into text itself, so the browser's speech recognition is not needed
        'transcribes': ai.can_transcribe(),
    })


def _number(raw, low, high):
    """The number sent, held between low and high; None when it is missing or not a number."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    return min(max(value, low), high)


def _read_answers(request, questions, allowed_seconds):
    """The answers the page sent (`questions` maps id → question): (entries, None) or (None, what is wrong)."""
    entries, seen = [], set()
    while f'question_{len(entries)}' in request.POST:
        index = len(entries)
        if index >= len(questions):
            return None, 'More answers than questions were sent.'
        try:
            question = questions[int(request.POST[f'question_{index}'])]
        except (KeyError, ValueError):
            return None, 'An answer belongs to an unknown question.'
        if question.pk in seen:
            return None, 'A question was answered twice.'
        seen.add(question.pk)
        audio = request.FILES.get(f'audio_{index}')
        if audio is not None:
            if audio.content_type not in AUDIO_EXTENSIONS:
                return None, 'A recording is not an audio file.'
            if audio.size > MAX_AUDIO_BYTES:
                return None, 'A recording is too big.'
        entries.append({
            'question': question,
            'transcript': (request.POST.get(f'transcript_{index}') or '').strip()[:MAX_TRANSCRIPT_LENGTH].rstrip(),
            'seconds': _number(request.POST.get(f'seconds_{index}'), 0, allowed_seconds + 5) or 0,
            'early': request.POST.get(f'early_{index}') == '1',
            'confidence': _number(request.POST.get(f'confidence_{index}'), 0, 1),
            'audio': audio,
            'audio_name': f'answer{AUDIO_EXTENSIONS[audio.content_type]}' if audio is not None else '',
        })
    if not entries:
        return None, 'No answers were sent.'
    return entries, None


@login_required
@require_POST
def finish(request, slug, part, set_pk):
    """Save a finished practice (answers, recordings, coins), ask the AI for feedback and say where the results are."""
    course = _speaking_course(request, slug)
    part = _part(part)
    session = PART_RULES[part]['session']
    if session is None:
        raise Http404
    speaking_set = _get_set(course, part, set_pk)
    questions = {question.pk: question for question in speaking_set.questions.all()}
    if not questions:
        raise Http404

    recent = SpeakingAttempt.objects.filter(user=request.user, created_at__gte=timezone.now() - timedelta(hours=1))
    if recent.count() >= MAX_ATTEMPTS_PER_HOUR:
        return JsonResponse({'error': 'You have practised a lot in the last hour. Please wait a little.'}, status=429)
    entries, problem = _read_answers(request, questions, session['talk'])
    if problem:
        return JsonResponse({'error': problem}, status=400)

    with transaction.atomic():
        # coins are paid only when every question was answered until its timer ended
        earned = len(entries) == len(questions) and not any(entry['early'] for entry in entries)
        attempt = SpeakingAttempt.objects.create(
            user=request.user, set=speaking_set, coins=len(entries) if earned else 0)
        for order, entry in enumerate(entries):
            answer = SpeakingAnswer(
                attempt=attempt, order=order, question=entry['question'].text, transcript=entry['transcript'],
                seconds=entry['seconds'], finished_early=entry['early'], confidence=entry['confidence'])
            if entry['audio'] is not None:
                answer.audio.save(entry['audio_name'], entry['audio'], save=False)
            answer.save()
        SpeakingPractice.objects.get_or_create(user=request.user, set=speaking_set)
    analyse_attempt(attempt)  # outside the transaction: the request to the AI can take a while
    return JsonResponse({'url': attempt.get_absolute_url()})


def _get_attempt(request, slug, attempt_pk):
    course = _speaking_course(request, slug)
    attempt = get_object_or_404(
        SpeakingAttempt.objects.select_related('set__course', 'user'), pk=attempt_pk, set__course=course)
    _own_or_admin(request, attempt)
    return course, attempt


@login_required
def result(request, slug, attempt_pk):
    """The results of one practice: what the student said and the AI feedback on every answer."""
    course, attempt = _get_attempt(request, slug, attempt_pk)
    part = SpeakingPart(attempt.set.part)
    answers = list(attempt.answers.all())
    return render(request, 'speaking/result.html', {
        'course': course,
        'part': part_info(part),
        'set': attempt.set,
        'attempt': attempt,
        'answers': answers,
        'questions': questions_label(len(answers)),
        # without a key asking again cannot work, so the page explains instead of offering a button
        'ai_ready': ai.is_configured(),
        'transcribes': ai.can_transcribe(),
    })


@login_required
@require_POST
def retry_feedback(request, slug, attempt_pk):
    """Ask the AI again for an attempt that has no feedback yet (it was down or was not set up at the time)."""
    attempt = _get_attempt(request, slug, attempt_pk)[1]
    if attempt.feedback_status != SpeakingAttempt.Feedback.READY:
        status = analyse_attempt(attempt)
        if status == SpeakingAttempt.Feedback.UNCONFIGURED:
            messages.error(request, 'The AI feedback is not turned on on this site yet. Your answers are saved: '
                                    'ask your teacher to turn it on, then try again.')
        elif status != SpeakingAttempt.Feedback.READY:
            messages.error(request, 'The AI feedback is still not available. Please try again a little later.')
    return redirect(attempt)


@login_required
def answer_audio(request, slug, answer_pk):
    """The recording of one answer, for its owner and for admins."""
    course = _speaking_course(request, slug)
    answer = get_object_or_404(
        SpeakingAnswer.objects.select_related('attempt__user'), pk=answer_pk, attempt__set__course=course)
    _own_or_admin(request, answer.attempt)
    if not answer.audio or not os.path.exists(answer.audio.path):
        raise Http404
    return file_response_with_range(request, answer.audio.path, content_type=answer.audio_content_type)
