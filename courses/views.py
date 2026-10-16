import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from speaking.views import speaking_hub
from writing.views import writing_hub

from .access import visible_course
from .grading import grade_exercise
from .models import Category, Course, Enrollment, Exercise, ExerciseResult, Part
from .passages import build_passage_blocks
from .streaming import file_response_with_range

PASSAGE_KINDS = (Part.Kind.PASSAGE_GAP, Part.Kind.PASSAGE_MIXED)
DEFAULT_PRACTICE_INTRO = "Choose a part, then pick an exercise. You get your score straight away."
PRACTICE_INTROS = {
    Category.LISTENING: (
        "Choose a part, then pick an exercise. Put on your headphones, listen and answer. "
        "You get your score straight away."
    ),
    Category.READING: "Choose a part, then pick an exercise. Each one is short and you get your score straight away.",
}


def _practice_parts(course, user):
    parts = list(course.parts.prefetch_related('exercises'))
    results = {}
    if parts and user.is_authenticated:
        results = {
            result.exercise_id: result
            for result in ExerciseResult.objects.filter(user=user, exercise__part__course=course)
        }
    for part in parts:
        part.exercise_list = list(part.exercises.all())
        for exercise in part.exercise_list:
            exercise.user_result = results.get(exercise.pk)
    return parts


_visible_course = visible_course


def _get_exercise(request, slug, part_number, exercise_number):
    course = _visible_course(request, slug=slug)
    exercise = get_object_or_404(
        Exercise.objects.select_related('part__course').annotate(questions_total=Count('questions')),
        part__course=course, part__number=part_number, number=exercise_number,
    )
    return course, exercise


def course_list(request):
    courses = Course.objects.filter(is_published=True)

    category = request.GET.get('category')
    if category in Category.values:
        courses = courses.filter(category=category)

    query = request.GET.get('q')
    if query:
        courses = courses.filter(title__icontains=query)

    context = {
        'courses': courses,
        'categories': Category.choices,
        'active_category': category,
        'query': query or '',
    }
    return render(request, 'courses/course_list.html', context)


def course_detail(request, slug):
    course = _visible_course(request, slug=slug)

    if course.category == Category.WRITING:
        return writing_hub(request, course)
    if course.category == Category.SPEAKING:
        return speaking_hub(request, course)

    parts = _practice_parts(course, request.user)
    if parts:
        return render(request, 'courses/practice.html', {
            'course': course,
            'parts': parts,
            'intro': PRACTICE_INTROS.get(course.category, DEFAULT_PRACTICE_INTRO),
        })

    is_enrolled = (
        request.user.is_authenticated
        and Enrollment.objects.filter(user=request.user, course=course).exists()
    )
    context = {
        'course': course,
        'learning_outcomes': course.learning_outcomes.all(),
        'skill_tags': course.skill_tags.all(),
        'is_enrolled': is_enrolled,
    }
    return render(request, 'courses/course_detail.html', context)


@login_required
def enroll(request, slug):
    course = get_object_or_404(Course, slug=slug, is_published=True)
    enrollment, created = Enrollment.objects.get_or_create(user=request.user, course=course)
    if created:
        course.enrolled_count = Course.objects.filter(pk=course.pk).first().enrolled_count + 1
        course.save(update_fields=['enrolled_count'])
        messages.success(request, f'"{course.title}" kursiga yozildingiz!')
    return redirect('courses:course_detail', slug=course.slug)


@login_required
def exercise_intro(request, slug, part_number, exercise_number):
    course, exercise = _get_exercise(request, slug, part_number, exercise_number)
    return render(request, 'courses/exercise_intro.html', {
        'course': course,
        'part': exercise.part,
        'exercise': exercise,
    })


@login_required
def exercise_play(request, slug, part_number, exercise_number):
    course, exercise = _get_exercise(request, slug, part_number, exercise_number)
    if not exercise.is_ready:
        return redirect('courses:exercise_intro', slug=slug, part_number=part_number, exercise_number=exercise_number)

    questions = list(exercise.questions.all())
    for index, question in enumerate(questions):
        question.number = exercise.part.first_question_number + index

    seconds = exercise.duration_minutes * 60
    context = {
        'course': course,
        'part': exercise.part,
        'exercise': exercise,
        'questions': questions,
        'choice_questions': questions,
        'option_list': exercise.option_list,
        'duration_seconds': seconds,
        'timer_label': f'{seconds // 60:02d}:{seconds % 60:02d}',
    }
    if exercise.part.kind in PASSAGE_KINDS:
        # in a "gaps, then test" exercise the test questions come under the text, not inside it
        gap_questions = [question for question in questions if not question.is_choice]
        context['choice_questions'] = [question for question in questions if question.is_choice]
        context['passage_blocks'] = build_passage_blocks(exercise.passage, gap_questions, number_of=lambda q: q.number)
    return render(request, 'courses/exercise_play.html', context)


@login_required
@require_POST
def exercise_submit(request, slug, part_number, exercise_number):
    course, exercise = _get_exercise(request, slug, part_number, exercise_number)
    if not exercise.is_ready:
        raise Http404

    review, score = grade_exercise(exercise, request.POST)
    total = len(review)

    best, created = ExerciseResult.objects.get_or_create(
        user=request.user, exercise=exercise, defaults={'score': score, 'total': total},
    )
    if not created and (score > best.score or total != best.total):
        best.score, best.total = score, total
        best.save()

    percent = round(score * 100 / total)
    if score == total:
        emoji, message = '🎉', 'Perfect score!'
    elif percent >= 70:
        emoji, message = '👏', 'Well done!'
    else:
        emoji, message = '💪', 'Keep going!'

    context = {
        'course': course,
        'part': exercise.part,
        'exercise': exercise,
        'option_list': exercise.option_list,
        'review': review,
        'score': score,
        'total': total,
        'percent': percent,
        'best': best,
        'emoji': emoji,
        'message': message,
        'time_used': _time_used_label(request.POST.get('time_used'), exercise.duration_minutes * 60),
    }
    if exercise.part.kind in PASSAGE_KINDS:
        gap_items = [item for item in review if item['type'] == 'gap']
        context['passage_blocks'] = build_passage_blocks(exercise.passage, gap_items, number_of=lambda item: item['number'])
    return render(request, 'courses/exercise_result.html', context)


def _time_used_label(raw, limit):
    """"01:05" for the seconds the page reports having been used (None when missing or not a number)."""
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        return None
    seconds = max(0, min(seconds, limit))
    return f'{seconds // 60:02d}:{seconds % 60:02d}'


def _serve_exercise_file(request, pk, field_name):
    exercise = get_object_or_404(Exercise.objects.select_related('part__course'), pk=pk)
    _visible_course(request, pk=exercise.part.course_id)
    field = getattr(exercise, field_name)
    if not field:
        raise Http404
    path = field.path
    if not os.path.exists(path):
        raise Http404
    return file_response_with_range(request, path)


@login_required
def exercise_audio(request, pk):
    return _serve_exercise_file(request, pk, 'audio')


@login_required
def exercise_image(request, pk):
    return _serve_exercise_file(request, pk, 'image')
