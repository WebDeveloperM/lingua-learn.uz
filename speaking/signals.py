from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import SpeakingAnswer


@receiver(post_delete, sender=SpeakingAnswer)
def delete_answer_recording(sender, instance, **kwargs):
    if instance.audio:
        instance.audio.storage.delete(instance.audio.name)
