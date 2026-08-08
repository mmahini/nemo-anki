from django.contrib import admin

from .models import ClassroomLink


@admin.register(ClassroomLink)
class ClassroomLinkAdmin(admin.ModelAdmin):
    list_display = ["id", "teacher", "student", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["teacher__email", "student__email"]
