from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.forms import inlineformset_factory

from courses.models import Course, Exercise, LearningOutcome, Part, Question, SkillTag
from courses.passages import MAX_GAPS, passage_answers

AUDIO_EXTENSIONS = ('mp3', 'wav', 'ogg', 'm4a', 'aac')
MAX_AUDIO_MB = 30
IMAGE_EXTENSIONS = ('png', 'jpg', 'jpeg', 'gif', 'webp')
MAX_IMAGE_MB = 8
DEFAULT_MAP_LETTERS = 9


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = [
            'title', 'category', 'level', 'cefr_badge', 'short_description',
            'about_this_course', 'course_description',
            'duration_text', 'language', 'publisher_name', 'is_cpd_accredited',
            'is_published', 'is_new',
        ]
        labels = {
            'title': 'Kurs nomi',
            'category': 'Skill (kategoriya)',
            'level': 'Daraja',
            'cefr_badge': 'CEFR nishoni',
            'short_description': 'Qisqa tavsif',
            'about_this_course': 'Kurs haqida (About This Course)',
            'course_description': 'Batafsil tavsif (Course Description)',
            'duration_text': 'Davomiyligi',
            'language': 'Til',
            'publisher_name': 'Nashr etuvchi',
            'is_cpd_accredited': 'CPD akkreditatsiyasi bor',
            'is_published': 'Saytda ko\'rsatish (nashr etish)',
            'is_new': '"YANGI" belgisini ko\'rsatish',
        }
        help_texts = {
            'title': '',
            'cefr_badge': 'Masalan: B2 Upper-Intermediate',
            'short_description': 'Kurs sarlavhasi ostida ko\'rinadi',
            'duration_text': 'Masalan: 1.5-3 Hours (Contains Video)',
            'is_published': 'O\'chirilsa, kurs qoralama bo\'ladi va faqat adminlarga ko\'rinadi',
            'is_new': '',
        }
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'Learn English: ...'}),
            'cefr_badge': forms.TextInput(attrs={'placeholder': 'B2 Upper-Intermediate'}),
            'short_description': forms.Textarea(attrs={'rows': 3}),
            'about_this_course': forms.Textarea(attrs={'rows': 5}),
            'course_description': forms.Textarea(attrs={'rows': 8}),
        }

    # Long texts whose section may be hidden from the page: when the browser did not send them, they are kept.
    OPTIONAL_TEXTS = ('about_this_course', 'course_description')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound:
            for name in self.OPTIONAL_TEXTS:
                if name not in self.data:
                    del self.fields[name]


LearningOutcomeFormSet = inlineformset_factory(
    Course, LearningOutcome, fields=['text'], extra=2, can_delete=True,
    widgets={'text': forms.TextInput(attrs={'placeholder': 'Masalan: Explain when to apply mixed conditionals'})},
)

SkillTagFormSet = inlineformset_factory(
    Course, SkillTag, fields=['name', 'highlighted'], extra=2, can_delete=True,
    widgets={'name': forms.TextInput(attrs={'placeholder': 'Masalan: English Grammar'})},
)


class ProgressForm(forms.Form):
    progress_percent = forms.IntegerField(min_value=0, max_value=100)


class PartForm(forms.ModelForm):
    number = forms.IntegerField(label='Part raqami', min_value=1, max_value=99)
    first_question_number = forms.IntegerField(label='Birinchi savol raqami', min_value=1, max_value=999)
    questions_count = forms.IntegerField(
        label='Mashqdagi savollar soni', min_value=1, max_value=60, required=False,
        widget=forms.NumberInput(attrs={'placeholder': 'Avtomatik'}),
        help_text=(
            'Mashq muharririda shuncha savol qatori ochiladi (masalan, 24–29-savollar uchun 6). Bo\'sh qoldirilsa, '
            'turiga qarab olinadi: A, B, C — 8, eshitib yozish — 6, ro\'yxatdan tanlash — 4, xarita — 5. '
            'Matn + test turida faqat matndan keyingi test savollari soni yoziladi (masalan, 34–35 uchun 2): '
            'bo\'sh joylar matnning o\'zidan olinadi. Ko\'proq kerak bo\'lsa, mashqda «+ Savol qo\'shish» tugmasi bor.'
        ),
    )

    class Meta:
        model = Part
        fields = [
            'number', 'name', 'icon', 'kind', 'first_question_number', 'questions_count', 'key_words_count',
            'instructions',
        ]
        labels = {
            'name': 'Nomi',
            'icon': 'Belgi (emoji)',
            'kind': 'Mashq turi',
            'key_words_count': 'Key vocabulary so\'zlari soni',
            'instructions': 'Umumiy ko\'rsatma',
        }
        help_texts = {
            'name': 'Masalan: Short replies',
            'icon': 'Masalan: 💬',
            'kind': 'Savollar qanday ko\'rinishi va qanday tekshirilishini belgilaydi.',
            'first_question_number': 'Savollar Part\'lar bo\'ylab davom etadi: 1-Part 1–8, 2-Part 9–14 bo\'lsa, 2-Part uchun 9 yozing.',
            'key_words_count': '«Key vocabulary · 50 words» belgisida ko\'rinadi. 0 bo\'lsa, belgi chiqmaydi.',
            'instructions': (
                'Shu Part\'dagi barcha mashqlarda ko\'rsatma sifatida chiqadi: Listening\'da audio ostida, Reading\'da matn '
                'tepasida (mashqning o\'zida boshqa matn yozish ham mumkin). **so\'z** qalin yoziladi.'
            ),
        }
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Short replies'}),
            'icon': forms.TextInput(attrs={'placeholder': '💬'}),
            'instructions': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, course, **kwargs):
        super().__init__(*args, **kwargs)
        self.course = course
        if not self.initial.get('questions_count'):
            self.initial['questions_count'] = None  # 0 means "by kind": show an empty box, not a 0

    def clean_number(self):
        number = self.cleaned_data['number']
        clash = Part.objects.filter(course=self.course, number=number).exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError('Bu raqamli Part allaqachon mavjud.')
        return number

    def clean_questions_count(self):
        return self.cleaned_data.get('questions_count') or 0

    def clean_kind(self):
        kind = self.cleaned_data['kind']
        if self.instance.pk and kind != self.instance.kind and Question.objects.filter(exercise__part=self.instance).exists():
            raise ValidationError(
                "Bu Part mashqlarida savollar bor. Turini o'zgartirishdan oldin ularning savollarini o'chiring: "
                "savollar turga qarab boshqacha saqlanadi."
            )
        return kind


def parse_options(text):
    return [line.strip() for line in (text or '').splitlines() if line.strip()]


def passage_problem(passage):
    """Why a Reading passage cannot be saved (None when it is fine or empty)."""
    if not passage.strip():
        return None
    answers = passage_answers(passage)
    if passage.count('[[') != passage.count(']]') or passage.count('[[') != len(answers) or not all(answers):
        return (
            "Qavslar mos kelmayapti yoki bo'sh: har bir bo'sh joy [[so'z]] ko'rinishida bo'lishi kerak "
            "(ikkita ochuvchi va ikkita yopuvchi kvadrat qavs, ichi bo'sh bo'lmasin)."
        )
    if not answers:
        return "Matnda bo'sh joy yo'q: o'quvchi yozadigan so'zni [[ikkita kvadrat qavs]] ichiga oling."
    if len(answers) > MAX_GAPS:
        return f"Bo'sh joylar soni {MAX_GAPS} tadan oshmasligi kerak (hozir {len(answers)} ta)."
    if any(len(answer) > Question._meta.get_field('answer').max_length for answer in answers):
        return "Bitta javob juda uzun: [[ ]] ichida faqat so'z yoki qisqa ibora bo'lsin."
    return None


class ExerciseContentForm(forms.ModelForm):
    duration_minutes = forms.IntegerField(label='Davomiyligi (daqiqa)', min_value=1, max_value=120)
    letters_count = forms.IntegerField(
        label='Javob harflari soni', min_value=0, max_value=Exercise.MAX_OPTIONS, required=False,
        help_text="Xaritadagi harflar A dan boshlanadi: 9 yozsangiz, A dan I gacha bo'ladi.",
    )
    remove_audio = forms.BooleanField(required=False, label='Mavjud audioni o\'chirish')
    remove_image = forms.BooleanField(required=False, label='Mavjud rasmni o\'chirish')

    class Meta:
        model = Exercise
        fields = [
            'audio', 'duration_minutes', 'instructions', 'title', 'options', 'image', 'letters_count', 'transcript',
            'passage',
        ]
        labels = {
            'audio': 'Audio fayl',
            'instructions': 'Shu mashq uchun ko\'rsatma',
            'title': 'Sarlavha',
            'options': 'Variantlar ro\'yxati',
            'image': 'Xarita rasmi',
            'transcript': 'Audio matni',
            'passage': 'Matn (Passage)',
        }
        help_texts = {
            'passage': (
                'Katta matnni shu yerga yozing yoki qo\'ying. O\'quvchi yozishi kerak bo\'lgan so\'zni ikkita kvadrat '
                'qavs ichiga oling: Although the [[town]] was small. O\'quvchida u o\'rnida «(Q1) 1 [kiritish joyi]» '
                'chiqadi, savollar Part\'ning birinchi savol raqamidan boshlab raqamlanadi. Bir nechta javob qabul '
                'qilinsa, ularni / bilan ajrating: [[town / city]]. Abzaslar bo\'sh qator bilan ajratiladi (oddiy Enter '
                'bo\'sh joy sifatida o\'qiladi, shuning uchun PDF\'dan ko\'chirilgan matn bir tekis oqadi). Bo\'sh joydan '
                'oldin yozilgan «1.» yoki «(Q1)» kabi raqam o\'quvchiga ikki marta chiqmasligi uchun olib tashlanadi.'
            ),
            'transcript': (
                'Ixtiyoriy. O\'quvchi natijalarni ko\'rganda «Transcript» bo\'limida chiqadi. Abzaslar bo\'sh qator bilan '
                'ajratiladi; to\'g\'ri javobli joylarni **ikkita yulduzcha** ichiga oling, ular sariq rangda ajralib turadi. '
                'Bo\'sh qoldirilsa, Transcript ko\'rinmaydi.'
            ),
            'instructions': 'Ixtiyoriy. Bo\'sh qoldirilsa, Part\'ning umumiy ko\'rsatmasi chiqadi. **so\'z** qalin yoziladi.',
            'title': 'Bo\'sh joylar tepasida chiqadi. Masalan: Video game review',
            'options': (
                f'Har qatorga bitta variant ({Exercise.MAX_OPTIONS} tagacha). Harflar (A, B, C...) avtomatik qo\'yiladi. '
                'Masalan: Arriving late for everything.'
            ),
        }
        widgets = {
            'audio': forms.FileInput(attrs={'accept': 'audio/*,.mp3,.wav,.ogg,.m4a,.aac'}),
            'image': forms.FileInput(attrs={'accept': 'image/*,.png,.jpg,.jpeg,.gif,.webp'}),
            'instructions': forms.Textarea(attrs={'rows': 3}),
            'title': forms.TextInput(attrs={'placeholder': 'Video game review'}),
            'options': forms.Textarea(attrs={'rows': 6}),
            'transcript': forms.Textarea(attrs={
                'rows': 10, 'placeholder': 'Woman: Is this your umbrella?\nMan: I\'m afraid **not**.',
            }),
            'passage': forms.Textarea(attrs={
                'rows': 16,
                'placeholder': 'Olivia likes traveling and visiting new places. Although the [[town]] was small, it was really wonderful...',
            }),
        }

    # The optional fields each kind of Part uses; everything else is removed from the form.
    KIND_FIELDS = {
        Part.Kind.GAP_FILL: ('title',),
        Part.Kind.MATCHING: ('title', 'options'),
        Part.Kind.MAP: ('image', 'letters_count', 'remove_image'),
        Part.Kind.PASSAGE_GAP: ('title', 'passage'),
        Part.Kind.PASSAGE_MIXED: ('title', 'passage'),
    }
    # Kinds whose passage has [[gaps]] in it (any other passage is just text to read).
    GAP_PASSAGE_KINDS = (Part.Kind.PASSAGE_GAP, Part.Kind.PASSAGE_MIXED)
    # Only Listening exercises have a recording (and so an audio file and its transcript).
    AUDIO_FIELDS = ('audio', 'remove_audio', 'transcript')

    def __init__(self, *args, kind=Part.Kind.CHOICE, with_audio=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.kind = kind
        used = self.KIND_FIELDS.get(kind, ())
        if kind == Part.Kind.CHOICE and not with_audio:
            used = ('title', 'passage')  # a Reading text with test questions under it
        for name in ('title', 'options', 'image', 'letters_count', 'remove_image', 'passage'):
            if name not in used:
                del self.fields[name]
        if not with_audio:
            for name in self.AUDIO_FIELDS:
                del self.fields[name]
        if kind in self.GAP_PASSAGE_KINDS:
            self.fields['title'].help_text = 'Matn tepasida chiqadi. Masalan: Olivia'
            self.fields['title'].widget.attrs['placeholder'] = 'Olivia'
        elif kind == Part.Kind.CHOICE and 'passage' in self.fields:
            self.fields['title'].help_text = 'Ixtiyoriy. Matn tepasida o\'rtada qalin chiqadi. Masalan: Eating meat'
            self.fields['title'].widget.attrs['placeholder'] = 'Eating meat'
            self.fields['passage'].help_text = (
                "Savollar uchun o'qiladigan matn (ixtiyoriy). Abzaslar bo'sh qator bilan ajratiladi; oddiy Enter "
                "bo'sh joy sifatida o'qiladi."
            )
            self.fields['passage'].widget.attrs['placeholder'] = 'Do you hate the idea of animal-free meat? Many people do...'
        elif kind == Part.Kind.MATCHING:
            self.fields['title'].help_text = (
                "Ixtiyoriy. Variantlar ro'yxati tepasida o'rtada qalin chiqadi (Headings uchun: Pedestrian Zones and Their Growth)."
            )
            self.fields['title'].widget.attrs['placeholder'] = 'Pedestrian Zones and Their Growth'
        if kind == Part.Kind.MAP and not self.instance.letters_count:
            self.initial['letters_count'] = DEFAULT_MAP_LETTERS

    def clean_passage(self):
        passage = self.cleaned_data.get('passage', '')
        problem = passage_problem(passage) if self.kind in self.GAP_PASSAGE_KINDS else None
        if problem:
            raise ValidationError(problem)
        return passage

    def clean_options(self):
        options = self.cleaned_data.get('options', '')
        if len(parse_options(options)) > Exercise.MAX_OPTIONS:
            raise ValidationError(f'Variantlar soni {Exercise.MAX_OPTIONS} tadan oshmasligi kerak.')
        return options

    def clean_letters_count(self):
        return self.cleaned_data.get('letters_count') or 0

    @staticmethod
    def _check_upload(upload, extensions, max_mb, label):
        if isinstance(upload, UploadedFile):
            extension = upload.name.rsplit('.', 1)[-1].lower() if '.' in upload.name else ''
            if extension not in extensions:
                raise ValidationError(f"Faqat {label} yuklash mumkin: {', '.join(extensions)}.")
            if upload.size > max_mb * 1024 * 1024:
                raise ValidationError(f"Fayl hajmi {max_mb} MB dan oshmasligi kerak.")
        return upload

    def clean_audio(self):
        return self._check_upload(self.cleaned_data.get('audio'), AUDIO_EXTENSIONS, MAX_AUDIO_MB, 'audio fayl')

    def clean_image(self):
        return self._check_upload(self.cleaned_data.get('image'), IMAGE_EXTENSIONS, MAX_IMAGE_MB, 'rasm')

    def save(self, commit=True):
        previous = {name: self.initial.get(name) for name in ('audio', 'image')}
        exercise = super().save(commit=False)
        for name in ('audio', 'image'):
            removed = self.cleaned_data.get(f'remove_{name}')
            if removed and not isinstance(self.cleaned_data.get(name), UploadedFile):
                setattr(exercise, name, '')
        if commit:
            exercise.save()
            for name, old in previous.items():
                if old and old.name and old.name != getattr(exercise, name).name:
                    old.storage.delete(old.name)
        return exercise


def _letter_choices(count):
    return [('', 'To\'g\'ri javob...')] + list(Question.Option.choices)[:count]


class ChoiceQuestionForm(forms.ModelForm):
    correct = forms.ChoiceField(label='To\'g\'ri javob', choices=_letter_choices(4))

    class Meta:
        model = Question
        fields = ['intro', 'text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct']
        widgets = {
            'intro': forms.TextInput(attrs={
                'placeholder': 'Savoldan oldingi sarlavha (ixtiyoriy): **Questions 21-24:** choose the correct answer A, B, C or D.',
            }),
            'text': forms.TextInput(attrs={'placeholder': 'Savol matni (ixtiyoriy)'}),
            'option_a': forms.TextInput(attrs={'placeholder': 'A variant'}),
            'option_b': forms.TextInput(attrs={'placeholder': 'B variant'}),
            'option_c': forms.TextInput(attrs={'placeholder': 'C variant'}),
            'option_d': forms.TextInput(attrs={'placeholder': 'D variant (ixtiyoriy)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('option_a', 'option_b', 'option_c'):
            self.fields[name].required = True

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('correct') == 'd' and not (cleaned.get('option_d') or '').strip():
            self.add_error('correct', "To'g'ri javob D, lekin D variant yozilmagan.")
        return cleaned


class GapQuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['intro', 'text', 'text_before', 'text_after', 'answer']
        widgets = {
            'intro': forms.TextInput(attrs={
                'placeholder': 'Shu qatordan oldingi oddiy matn (gapsiz, ixtiyoriy): Labyrinths represent a journey through life.',
            }),
            'text': forms.TextInput(attrs={'placeholder': 'Sarlavha, masalan: Action takes place in:'}),
            'text_before': forms.TextInput(attrs={'placeholder': 'Oldingi matn (a, the, www.)'}),
            'text_after': forms.TextInput(attrs={'placeholder': 'Keyingi matn (.com)'}),
            'answer': forms.TextInput(attrs={'placeholder': 'To\'g\'ri javob (bir nechta bo\'lsa: space / outer space)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['answer'].required = True


class MatchQuestionForm(forms.ModelForm):
    correct = forms.ChoiceField(label='To\'g\'ri javob', choices=_letter_choices(Exercise.MAX_OPTIONS))

    class Meta:
        model = Question
        fields = ['label', 'text', 'correct']
        widgets = {
            'label': forms.TextInput(attrs={'placeholder': 'Qalin sarlavha (ixtiyoriy): Paragraph I'}),
            'text': forms.Textarea(attrs={
                'rows': 3, 'placeholder': 'Savol matni: Speaker 1 yoki butun abzas (Willow Farm is perfect for families...)',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['text'].required = True


class MapQuestionForm(MatchQuestionForm):
    class Meta(MatchQuestionForm.Meta):
        fields = ['text', 'correct']
        widgets = {'text': forms.TextInput(attrs={'placeholder': 'Masalan: Gift shop'})}


CHOICE_FIELDS = ['intro', 'text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct']
QUESTION_FORMS = {
    Part.Kind.CHOICE: (ChoiceQuestionForm, CHOICE_FIELDS),
    Part.Kind.GAP_FILL: (GapQuestionForm, ['intro', 'text', 'text_before', 'text_after', 'answer']),
    Part.Kind.MATCHING: (MatchQuestionForm, ['label', 'text', 'correct']),
    Part.Kind.MAP: (MapQuestionForm, ['text', 'correct']),
    # the test questions that follow the gaps of a text are ordinary choice questions
    Part.Kind.PASSAGE_MIXED: (ChoiceQuestionForm, CHOICE_FIELDS),
}


def question_formset_class(kind, blank_rows):
    """Formset for the Part's kind, followed by `blank_rows` empty rows for questions still to be written."""
    form, fields = QUESTION_FORMS[kind]
    return inlineformset_factory(
        Exercise, Question, form=form, fields=fields, extra=blank_rows, can_delete=True,
    )


def letter_problem(kind, cleaned_data, questions):
    """Why the correct letters of a matching/map exercise do not fit its letters (None when they do)."""
    letters = []
    for form in questions.forms:
        if form in questions.deleted_forms or (not form.instance.pk and not form.has_changed()):
            continue
        letters.append(form.cleaned_data.get('correct'))
    if not letters:
        return None

    if kind == Part.Kind.MAP:
        available = cleaned_data.get('letters_count') or 0
        too_few = "Savollar uchun kamida 2 ta harf kiriting («Javob harflari soni»)."
        outside = "To'g'ri javob harfi xaritadagi harflardan tashqarida ({} ta harf bor)."
    else:
        available = len(parse_options(cleaned_data.get('options', '')))
        too_few = 'Savollar uchun kamida 2 ta variant kiriting.'
        outside = "To'g'ri javob harfi variantlar ro'yxatidan tashqarida ({} ta variant bor)."
    if available < 2:
        return too_few
    if any(ord(letter) - ord('a') >= available for letter in letters if letter):
        return outside.format(available)
    return None
