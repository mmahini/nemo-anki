from django.contrib import admin

from .models import Deck, DeckConfig


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "language", "config", "created_at")
    list_filter = ("language",)
    search_fields = ("name", "user__email")


@admin.register(DeckConfig)
class DeckConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "new_per_day", "reviews_per_day", "starting_ease")
    search_fields = ("name", "user__email")
