from django import template

from accounts.models import Role, User

register = template.Library()


@register.simple_tag
def pending_students_count():
    return User.objects.filter(role=Role.STUDENT, is_active=False).count()
