from django import forms
from django.db import transaction

from writing.models import Slot, TASK_RULES, WritingTask, WritingTest

# The text fields a task has, and how the panel asks for them. Tasks 1.1 and 1.2 answer a letter, so they have all four.
TASK_FIELDS = {
    'instruction': {
        'label': 'Topshiriq', 'rows': 3,
        'help': "O'quvchi nima yozishi kerak (qalin chiqadi). Masalan: Write a short email to your friend... Write about 50 words.",
    },
    'context': {
        'label': 'Kontekst (kichik yozuv)', 'rows': 0,
        'help': "Xat tepasida kichik yozuv bilan chiqadi. Masalan: You are a member of the Travel Club at your language center...",
    },
    'prompt': {
        'label': 'Xat / matn (o\'quvchi javob yozadigan)', 'rows': 8,
        'help': "Xatning o'zi. Masalan: Dear Member, We are planning our trips... Qator uzilishlari saqlanadi.",
    },
    'sample_answer': {
        'label': 'Namuna javob', 'rows': 8,
        'help': "Ixtiyoriy namuna javob (o'quvchida «Sample answer» bo'limida chiqadi). Xatning o'zini bu yerga emas, "
                "«Xat / matn» ga yozing. Bo'sh qoldirilsa, bo'lim chiqmaydi.",
    },
}
# Part 2 is a single task text: no letter, no context and no sample answer.
PART_2_TASK = {
    'label': 'Topshiriq', 'rows': 5,
    'help': "O'quvchiga qalin yozuvda chiqadi. Masalan: You are participating in an online discussion for language "
            "learners. The question is: “Some people say a vegetarian diet is better for health. Do you agree?” "
            "Post your response, giving reasons and examples. «Write 180–200 words.» qatori uning ostidan o'zi qo'shiladi.",
}


def slot_fields(slot):
    """The names of the form fields a task of this slot has."""
    return list(TASK_FIELDS) if TASK_RULES[slot]['letter'] else ['instruction']


def field_spec(slot, name):
    return PART_2_TASK if name == 'instruction' and not TASK_RULES[slot]['letter'] else TASK_FIELDS[name]


def field_name(slot, name):
    return f'task{slot}_{name}'


class WritingTestForm(forms.ModelForm):
    """A test and its three tasks on one page: a task whose fields are all empty simply does not exist."""

    class Meta:
        model = WritingTest
        fields = ['title', 'date', 'shift', 'topic', 'duration_minutes']
        labels = {
            'title': 'Test nomi', 'date': 'Sana', 'shift': 'Smena', 'topic': 'Part 2 mavzusi',
            'duration_minutes': 'Davomiyligi (daqiqa)',
        }
        help_texts = {
            'title': 'Masalan: Travel Club',
            'topic': "Ro'yxatda «Part 2: ...» ko'rinishida chiqadi. Masalan: Is a vegetarian diet better for health?",
        }
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Travel Club'}),
            'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'topic': forms.TextInput(attrs={'placeholder': 'Is a vegetarian diet better for health?'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['duration_minutes'] = forms.IntegerField(
            label='Davomiyligi (daqiqa)', min_value=1, max_value=240, initial=60,
            help_text='Uchala topshiriq uchun umumiy vaqt.',
        )
        existing = {task.slot: task for task in self.instance.tasks.all()} if self.instance.pk else {}
        for slot in Slot.values:
            task = existing.get(slot)
            for name in slot_fields(slot):
                spec = field_spec(slot, name)
                if spec['rows']:
                    widget = forms.Textarea(attrs={'rows': spec['rows']})
                    field = forms.CharField(label=spec['label'], required=False, widget=widget, help_text=spec['help'])
                else:
                    field = forms.CharField(
                        label=spec['label'], required=False, max_length=500, help_text=spec['help'],
                        widget=forms.TextInput(),
                    )
                field.initial = getattr(task, name) if task else ''
                self.fields[field_name(slot, name)] = field

    def clean(self):
        cleaned = super().clean()
        for slot in Slot.values:
            used = any((cleaned.get(field_name(slot, name)) or '').strip() for name in slot_fields(slot))
            if used and not (cleaned.get(field_name(slot, 'instruction')) or '').strip():
                self.add_error(
                    field_name(slot, 'instruction'),
                    f"{TASK_RULES[slot]['label']} to'ldirilgan, lekin «Topshiriq» yozilmagan.",
                )
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        test = super().save()
        for slot in Slot.values:
            values = {
                name: (self.cleaned_data.get(field_name(slot, name)) or '').strip() for name in slot_fields(slot)
            }
            if any(values.values()):
                # only this slot's fields are written: whatever else an older task row holds stays as it was
                WritingTask.objects.update_or_create(test=test, slot=slot, defaults=values)
            else:
                WritingTask.objects.filter(test=test, slot=slot).delete()
        return test

    def task_sections(self):
        """The three tasks as the template shows them: (label, what it asks for, its bound fields)."""
        return [
            {
                'slot': slot,
                'label': TASK_RULES[slot]['label'],
                'description': f"{TASK_RULES[slot]['about']}, {TASK_RULES[slot]['target']} words",
                'note': (
                    "Hamma maydon bo'sh qolsa, bu topshiriq testda bo'lmaydi." if TASK_RULES[slot]['letter']
                    else "Bo'sh qolsa, bu topshiriq testda bo'lmaydi."
                ),
                'fields': [self[field_name(slot, name)] for name in slot_fields(slot)],
            }
            for slot in Slot.values
        ]
