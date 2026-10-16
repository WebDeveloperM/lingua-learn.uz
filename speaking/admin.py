from django.contrib import admin

from .models import SpeakingAnswer, SpeakingAttempt, SpeakingPractice, SpeakingQuestion, SpeakingSet


class SpeakingQuestionInline(admin.TabularInline):
    model = SpeakingQuestion
    extra = 0


@admin.register(SpeakingSet)
class SpeakingSetAdmin(admin.ModelAdmin):
    list_display = ('course', 'part', 'number')
    list_filter = ('course', 'part')
    inlines = [SpeakingQuestionInline]


@admin.register(SpeakingPractice)
class SpeakingPracticeAdmin(admin.ModelAdmin):
    list_display = ('user', 'set', 'practised_at')


class SpeakingAnswerInline(admin.TabularInline):
    model = SpeakingAnswer
    extra = 0


@admin.register(SpeakingAttempt)
class SpeakingAttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'set', 'created_at', 'coins', 'feedback_status')
    list_filter = ('feedback_status', 'set__part')
    inlines = [SpeakingAnswerInline]
