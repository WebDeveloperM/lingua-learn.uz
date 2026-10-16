from django.contrib import admin

from .models import SpeakingPractice, SpeakingQuestion, SpeakingSet


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
