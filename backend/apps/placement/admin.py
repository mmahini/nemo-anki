from django.contrib import admin

from .models import PlacementAttempt, PlacementQuestion


class PlacementQuestionInline(admin.TabularInline):
    model = PlacementQuestion
    extra = 0
    readonly_fields = [
        "order", "section", "level_tag", "question_text", "correct_choice_index", "user_choice_index",
    ]


@admin.register(PlacementAttempt)
class PlacementAttemptAdmin(admin.ModelAdmin):
    list_display = [
        "id", "user", "language", "length", "status", "estimated_level",
        "correct_count", "total_count", "created_at",
    ]
    list_filter = ["language", "length", "status", "estimated_level"]
    inlines = [PlacementQuestionInline]
