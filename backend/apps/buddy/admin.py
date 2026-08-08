from django.contrib import admin

from .models import BuddyLink


@admin.register(BuddyLink)
class BuddyLinkAdmin(admin.ModelAdmin):
    list_display = ["id", "requester", "recipient", "status", "created_at", "last_nudge_at"]
    list_filter = ["status"]
    search_fields = ["requester__email", "recipient__email"]
