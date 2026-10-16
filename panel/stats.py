from django.db.models import Count, IntegerField, Q, Sum
from django.db.models.functions import Coalesce

from accounts.models import Role, User


def students_with_stats():
    """Students annotated with course count, completed courses and score.

    Score is the sum of progress percentages over all enrollments (0-100 per course).
    """
    return User.objects.filter(role=Role.STUDENT).annotate(
        courses_count=Count('enrollments'),
        completed_count=Count('enrollments', filter=Q(enrollments__progress_percent=100)),
        score=Coalesce(Sum('enrollments__progress_percent'), 0, output_field=IntegerField()),
    )


def student_leaderboard(limit=None):
    """Active students ranked by score; equal score and completed courses share a rank."""
    students = students_with_stats().filter(is_active=True).order_by(
        '-score', '-completed_count', 'date_joined', 'pk',
    )
    if limit:
        students = students[:limit]

    rows = []
    previous_key = None
    rank = 0
    for position, student in enumerate(students, start=1):
        key = (student.score, student.completed_count)
        if key != previous_key:
            rank, previous_key = position, key
        rows.append({'rank': rank, 'student': student})
    return rows
