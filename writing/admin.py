from django.contrib import admin

from .models import WritingAnswer, WritingSubmission, WritingTask, WritingTest


class WritingTaskInline(admin.TabularInline):
    model = WritingTask
    extra = 0


@admin.register(WritingTest)
class WritingTestAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'shift', 'course')
    list_filter = ('course', 'shift')
    inlines = [WritingTaskInline]


class WritingAnswerInline(admin.TabularInline):
    model = WritingAnswer
    extra = 0


@admin.register(WritingSubmission)
class WritingSubmissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'test', 'sent_at')
    inlines = [WritingAnswerInline]
