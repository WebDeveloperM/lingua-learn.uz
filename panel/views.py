from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.models import Role, User
from courses.models import Category, Course, Enrollment, Exercise
from writing.models import WritingSubmission

from .decorators import admin_required
from .forms import CourseForm, LearningOutcomeFormSet, ProgressForm, SkillTagFormSet
from .speaking_views import speaking_part_rows
from .stats import student_leaderboard, students_with_stats
from .utils import save_ordered

STUDENTS_PER_PAGE = 15
COURSES_PER_PAGE = 10
STUDENT_ENROLLMENTS = Q(enrollments__user__role=Role.STUDENT)


def _paginate(request, queryset, per_page):
    page_obj = Paginator(queryset, per_page).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return page_obj, params.urlencode()


def _redirect_back(request, default):
    next_url = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(default)


@admin_required
def dashboard(request):
    students = User.objects.filter(role=Role.STUDENT)
    pending = students.filter(is_active=False)
    student_enrollments = Enrollment.objects.filter(user__role=Role.STUDENT)
    week_ago = timezone.now() - timedelta(days=7)

    return render(request, 'panel/dashboard.html', {
        'total_students': students.count(),
        'active_students': students.filter(is_active=True).count(),
        'pending_count': pending.count(),
        'new_this_week': students.filter(date_joined__gte=week_ago).count(),
        'courses_total': Course.objects.count(),
        'courses_published': Course.objects.filter(is_published=True).count(),
        'enrollments_total': student_enrollments.count(),
        'completed_total': student_enrollments.filter(progress_percent=100).count(),
        'pending_students': pending.order_by('-date_joined')[:5],
        'top_students': student_leaderboard(limit=5),
    })


@admin_required
def student_list(request):
    all_students = User.objects.filter(role=Role.STUDENT)
    counts = {
        'all': all_students.count(),
        'active': all_students.filter(is_active=True).count(),
        'pending': all_students.filter(is_active=False).count(),
    }

    status = request.GET.get('status', 'all')
    if status not in counts:
        status = 'all'
    query = request.GET.get('q', '').strip()

    students = students_with_stats().order_by('-date_joined')
    if status == 'active':
        students = students.filter(is_active=True)
    elif status == 'pending':
        students = students.filter(is_active=False)
    if query:
        students = students.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query)
        )

    page_obj, query_string = _paginate(request, students, STUDENTS_PER_PAGE)
    return render(request, 'panel/student_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'counts': counts,
        'status': status,
        'query': query,
    })


@admin_required
def student_detail(request, pk):
    student = get_object_or_404(students_with_stats(), pk=pk)
    enrollments = student.enrollments.select_related('course').order_by('-enrolled_at')
    return render(request, 'panel/student_detail.html', {
        'student': student,
        'enrollments': enrollments,
    })


@admin_required
@require_POST
def student_toggle_active(request, pk):
    student = get_object_or_404(User, pk=pk, role=Role.STUDENT)
    student.is_active = not student.is_active
    student.save(update_fields=['is_active'])
    state = 'faollashtirildi' if student.is_active else 'faolsizlantirildi'
    messages.success(request, f"{student.get_full_name() or student.email} {state}.")
    return _redirect_back(request, 'panel:student_list')


@admin_required
@require_POST
def student_delete(request, pk):
    student = get_object_or_404(User, pk=pk, role=Role.STUDENT)
    name = student.get_full_name() or student.email
    student.delete()
    messages.success(request, f"{name} o'chirildi.")
    return redirect('panel:student_list')


@admin_required
@require_POST
def enrollment_progress(request, pk):
    enrollment = get_object_or_404(Enrollment, pk=pk, user__role=Role.STUDENT)
    form = ProgressForm(request.POST)
    if form.is_valid():
        enrollment.progress_percent = form.cleaned_data['progress_percent']
        enrollment.save(update_fields=['progress_percent'])
        messages.success(request, "Progress saqlandi.")
    else:
        messages.error(request, "Progress 0 dan 100 gacha butun son bo'lishi kerak.")
    return redirect('panel:student_detail', pk=enrollment.user_id)


@admin_required
def rating(request):
    return render(request, 'panel/rating.html', {'rows': student_leaderboard()})


@admin_required
def course_list(request):
    all_courses = Course.objects.all()
    counts = {
        'all': all_courses.count(),
        'published': all_courses.filter(is_published=True).count(),
        'draft': all_courses.filter(is_published=False).count(),
    }

    status = request.GET.get('status', 'all')
    if status not in counts:
        status = 'all'
    category = request.GET.get('category', '')
    if category not in Category.values:
        category = ''
    query = request.GET.get('q', '').strip()

    courses = Course.objects.annotate(
        students_count=Count('enrollments', filter=STUDENT_ENROLLMENTS, distinct=True),
        outcomes_count=Count('learning_outcomes', distinct=True),
    ).order_by('-created_at', '-pk')
    if status == 'published':
        courses = courses.filter(is_published=True)
    elif status == 'draft':
        courses = courses.filter(is_published=False)
    if category:
        courses = courses.filter(category=category)
    if query:
        courses = courses.filter(title__icontains=query)

    page_obj, query_string = _paginate(request, courses, COURSES_PER_PAGE)
    return render(request, 'panel/course_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'counts': counts,
        'status': status,
        'category': category,
        'categories': Category.choices,
        'query': query,
    })


def _course_parts(course):
    exercises = Exercise.objects.select_related('part__course').annotate(questions_total=Count('questions'))
    parts = list(course.parts.prefetch_related(Prefetch('exercises', queryset=exercises)))
    for part in parts:
        part.exercise_list = list(part.exercises.all())
        part.ready_count = sum(1 for exercise in part.exercise_list if exercise.is_ready)
    return parts


def _section_data(request, prefix):
    """The POST data of an optional formset section, or None when the page did not send that section.

    The outcomes and tags sections can be hidden in the template; a section the browser never sent is left as it is.
    """
    return request.POST if f'{prefix}-TOTAL_FORMS' in request.POST else None


def _course_form_view(request, course=None):
    parent = course or Course()
    if request.method == 'POST':
        form = CourseForm(request.POST, instance=course)
        outcomes = LearningOutcomeFormSet(_section_data(request, 'outcomes'), instance=parent, prefix='outcomes')
        tags = SkillTagFormSet(_section_data(request, 'tags'), instance=parent, prefix='tags')
        sections_valid = all(section.is_valid() for section in (outcomes, tags) if section.is_bound)
        if form.is_valid() and sections_valid:
            with transaction.atomic():
                saved = form.save()
                for section in (outcomes, tags):
                    if section.is_bound:
                        save_ordered(section, course=saved)
            if course is None:
                messages.success(
                    request, f'"{saved.title}" kursi yaratildi. Endi pastdan Part va mashqlarni qo\'shishingiz mumkin.',
                )
                return redirect('panel:course_edit', pk=saved.pk)
            messages.success(request, f'"{saved.title}" kursi saqlandi.')
            return redirect('panel:course_list')
    else:
        form = CourseForm(instance=course)
        outcomes = LearningOutcomeFormSet(instance=parent, prefix='outcomes')
        tags = SkillTagFormSet(instance=parent, prefix='tags')

    context = {
        'form': form,
        'outcomes': outcomes,
        'tags': tags,
        'course': course,
        'parts': _course_parts(course) if course else [],
    }
    if course and course.category == Category.WRITING:
        context['writing_tests'] = course.writing_tests.annotate(
            task_count=Count('tasks', distinct=True), submission_count=Count('submissions', distinct=True),
        )
        context['submissions_count'] = WritingSubmission.objects.filter(test__course=course).count()
    if course and course.category == Category.SPEAKING:
        context['speaking_parts'] = speaking_part_rows(course)
    return render(request, 'panel/course_form.html', context)


@admin_required
def course_create(request):
    return _course_form_view(request)


@admin_required
def course_edit(request, pk):
    return _course_form_view(request, get_object_or_404(Course, pk=pk))


@admin_required
@require_POST
def course_toggle_published(request, pk):
    course = get_object_or_404(Course, pk=pk)
    course.is_published = not course.is_published
    course.save(update_fields=['is_published'])
    state = 'nashr etildi' if course.is_published else 'qoralamaga o\'tkazildi'
    messages.success(request, f'"{course.title}" {state}.')
    return _redirect_back(request, 'panel:course_list')


@admin_required
@require_POST
def course_delete(request, pk):
    course = get_object_or_404(Course, pk=pk)
    title = course.title
    course.delete()
    messages.success(request, f'"{title}" kursi o\'chirildi.')
    return redirect('panel:course_list')
