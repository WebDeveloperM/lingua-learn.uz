from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Exercise


@receiver(post_delete, sender=Exercise)
def delete_exercise_files(sender, instance, **kwargs):
    for field in (instance.audio, instance.image):
        if field:
            field.storage.delete(field.name)
