from django.contrib import admin

from .models import Card, ReviewLog


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ("front", "card_type", "article", "deck", "state", "due", "interval_days")
    list_filter = ("card_type", "state", "article", "language")
    search_fields = ("front", "back", "deck__name")


@admin.register(ReviewLog)
class ReviewLogAdmin(admin.ModelAdmin):
    list_display = ("card", "user", "rating", "state_before", "state_after", "reviewed_at")
    list_filter = ("rating",)
    search_fields = ("card__front", "user__email")
