from django import forms
from django.db import transaction
from django.forms import formset_factory

from speaking.models import SpeakingQuestion, SpeakingSet

MAX_QUESTIONS = 12
MAX_QUESTION_LENGTH = 300


class SetForm(forms.Form):
    """One set of a part: its questions, one per line."""

    set_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    questions = forms.CharField(
        label='Savollar', required=False, widget=forms.Textarea(attrs={'rows': 4}),
        help_text="Har qatorga bitta savol (odatda 3 ta). Masalan: What do you do on the weekends?",
    )
    delete = forms.BooleanField(required=False, label="Setni o'chirish (saqlaganda o'chadi)")

    def clean_questions(self):
        lines = [line.strip() for line in self.cleaned_data['questions'].splitlines() if line.strip()]
        if len(lines) > MAX_QUESTIONS:
            raise forms.ValidationError(f"Bir setda {MAX_QUESTIONS} tadan ko'p savol bo'lmaydi.")
        for line in lines:
            if len(line) > MAX_QUESTION_LENGTH:
                raise forms.ValidationError(f"Savol {MAX_QUESTION_LENGTH} belgidan oshmasligi kerak: «{line[:40]}…»")
        return lines


SetFormSet = formset_factory(SetForm, extra=1)


def questions_text(speaking_set):
    return '\n'.join(question.text for question in speaking_set.questions.all())


def sync_questions(speaking_set, lines):
    """Make the set's questions the given lines, keeping the rows (and what points at them) of unchanged places."""
    current = list(speaking_set.questions.all())
    for order, text in enumerate(lines):
        if order >= len(current):
            SpeakingQuestion.objects.create(set=speaking_set, order=order, text=text)
        elif current[order].text != text:
            current[order].text = text
            current[order].save(update_fields=['text'])
    for surplus in current[len(lines):]:
        surplus.delete()


@transaction.atomic
def save_sets(course, part, formset):
    """Save the rows of the part page: edit the questions of the sets that are there, drop the ones marked for
    deletion and add the new row as the next set. A set whose questions were all removed stays (students do not see
    it) until it is deleted on purpose."""
    existing = {speaking_set.pk: speaking_set for speaking_set in SpeakingSet.objects.filter(course=course, part=part)}
    next_number = max((speaking_set.number for speaking_set in existing.values()), default=0) + 1
    for form in formset:
        lines = form.cleaned_data.get('questions') or []
        set_id = form.cleaned_data.get('set_id')
        if set_id:
            speaking_set = existing.get(set_id)
            if speaking_set is None:  # not a set of this part: not ours to touch
                continue
            if form.cleaned_data.get('delete'):
                speaking_set.delete()
            else:
                sync_questions(speaking_set, lines)
        elif lines:
            speaking_set = SpeakingSet.objects.create(course=course, part=part, number=next_number)
            next_number += 1
            sync_questions(speaking_set, lines)
