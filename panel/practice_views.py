from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Max, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from courses.models import Course, Exercise, Part, Question
from courses.passages import passage_answers, sync_passage_questions

from .decorators import admin_required
from .forms import ExerciseContentForm, PartForm, letter_problem, question_formset_class
from .utils import save_ordered


ROW_TEMPLATES = {
    Part.Kind.CHOICE: 'panel/_question_row.html',
    Part.Kind.GAP_FILL: 'panel/_gap_row.html',
    Part.Kind.MATCHING: 'panel/_match_row.html',
    Part.Kind.MAP: 'panel/_match_row.html',
    Part.Kind.PASSAGE_MIXED: 'panel/_question_row.html',
}
PASSAGE_KINDS = (Part.Kind.PASSAGE_GAP, Part.Kind.PASSAGE_MIXED)
# Kinds whose answers are letters, and the form field that defines which letters exist.
LETTER_FIELDS = {Part.Kind.MATCHING: 'options', Part.Kind.MAP: 'letters_count'}


def _next_number(queryset):
    return (queryset.aggregate(top=Max('number'))['top'] or 0) + 1


def _suggest_first_question_number(course):
    """Questions continue from Part to Part, so suggest where the previous Part's questions end."""
    previous = course.parts.order_by('-number').first()
    if previous is None:
        return 1
    per_exercise = Question.objects.filter(exercise__part=previous).values('exercise').annotate(total=Count('pk'))
    longest = per_exercise.aggregate(top=Max('total'))['top'] or 0
    return previous.first_question_number + longest


def _part_form_view(request, course, part=None):
    if request.method == 'POST':
        form = PartForm(request.POST, instance=part, course=course)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.course = course
            saved.save()
            messages.success(request, f'Part {saved.number} saqlandi.')
            return redirect('panel:part_edit', pk=saved.pk)
    else:
        initial = {} if part else {
            'number': _next_number(course.parts),
            'first_question_number': _suggest_first_question_number(course),
        }
        form = PartForm(instance=part, course=course, initial=initial)

    exercises = []
    if part:
        queryset = Exercise.objects.filter(part=part).select_related('part__course').annotate(questions_total=Count('questions'))
        exercises = list(queryset)
    return render(request, 'panel/part_form.html', {
        'form': form,
        'course': course,
        'part': part,
        'exercises': exercises,
    })


@admin_required
def part_create(request, course_pk):
    return _part_form_view(request, get_object_or_404(Course, pk=course_pk))


@admin_required
def part_edit(request, pk):
    part = get_object_or_404(Part.objects.select_related('course'), pk=pk)
    return _part_form_view(request, part.course, part)


@admin_required
@require_POST
def part_delete(request, pk):
    part = get_object_or_404(Part.objects.select_related('course'), pk=pk)
    course = part.course
    label = f'Part {part.number} · {part.name}'
    part.delete()
    messages.success(request, f'{label} o\'chirildi.')
    return redirect('panel:course_edit', pk=course.pk)


@admin_required
@require_POST
def exercise_add(request, pk):
    part = get_object_or_404(Part, pk=pk)
    exercise = Exercise.objects.create(part=part, number=_next_number(part.exercises))
    messages.success(request, f'Exercise {exercise.number} qo\'shildi. Endi audio va savollarni kiriting.')
    return redirect('panel:exercise_edit', pk=exercise.pk)


@admin_required
def exercise_edit(request, pk):
    exercise = get_object_or_404(Exercise.objects.select_related('part__course'), pk=pk)
    part = exercise.part
    course = part.course
    # The questions of a Reading passage are its [[gaps]]: they are not typed as rows but generated on save.
    # A "gaps, then test" Part also has ordinary choice rows, which come after the gaps.
    from_passage = part.kind in PASSAGE_KINDS
    has_rows = part.kind != Part.Kind.PASSAGE_GAP
    gap_total = exercise.questions.filter(option_a='').count() if from_passage else 0
    formset_class = None
    formset_options = {}
    if has_rows:
        rows = exercise.questions.exclude(option_a='') if from_passage else exercise.questions.all()
        # Open the editor with as many rows as the Part's exercises have questions (never a spare one beyond that:
        # "+ Savol qo'shish" adds more), so a 6-question Part does not show rows 30 and 31.
        # (After a text with gaps only the test questions are rows, and only they are counted.)
        blank_rows = max(part.expected_questions - rows.count(), 0)
        formset_class = question_formset_class(part.kind, blank_rows)
        formset_options = {'instance': exercise, 'prefix': 'questions', 'queryset': rows}
    form_options = {'kind': part.kind, 'with_audio': part.needs_audio}

    if request.method == 'POST':
        form = ExerciseContentForm(request.POST, request.FILES, instance=exercise, **form_options)
        questions = formset_class(request.POST, **formset_options) if has_rows else None
        valid = form.is_valid() and (questions is None or questions.is_valid())
        letter_field = LETTER_FIELDS.get(part.kind)
        if valid and letter_field:
            problem = letter_problem(part.kind, form.cleaned_data, questions)
            if problem:
                form.add_error(letter_field, problem)
                valid = False
        if valid:
            with transaction.atomic():
                form.save()
                if from_passage:
                    sync_passage_questions(exercise)
                if has_rows:
                    save_ordered(
                        questions, start=len(passage_answers(exercise.passage)) if from_passage else 0,
                        exercise=exercise,
                    )
            messages.success(request, 'Mashq saqlandi.')
            return redirect('panel:exercise_edit', pk=exercise.pk)
    else:
        form = ExerciseContentForm(instance=exercise, **form_options)
        questions = formset_class(**formset_options) if has_rows else None

    gaps = []
    if from_passage:
        gaps = [
            {'number': part.first_question_number + index, 'answer': question.answer}
            for index, question in enumerate(exercise.questions.filter(option_a=''))
        ]
    return render(request, 'panel/exercise_form.html', {
        'form': form,
        'questions': questions,
        'row_template': ROW_TEMPLATES.get(part.kind),
        'row_start': part.first_question_number + gap_total,  # the number of the first row of the questions card
        'gaps': gaps,
        'exercise': exercise,
        'part': part,
        'course': course,
        'student_url': reverse('courses:exercise_intro', args=[course.slug, part.number, exercise.number]),
    })


@admin_required
@require_POST
def exercise_delete(request, pk):
    exercise = get_object_or_404(Exercise.objects.select_related('part'), pk=pk)
    part = exercise.part
    number = exercise.number
    exercise.delete()
    messages.success(request, f'Exercise {number} o\'chirildi.')
    return redirect('panel:part_edit', pk=part.pk)
