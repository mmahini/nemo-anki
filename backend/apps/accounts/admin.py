from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import EmailOTP, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "display_name", "is_active", "is_staff", "date_joined")
    search_fields = ("email", "display_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("display_name", "ui_language")}),
        ("Feature flags", {"fields": ("feature_flags",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        # Clearing onboarded_at sends this user back through the welcome flow —
        # handy for re-testing it against a real account.
        ("Important dates", {"fields": ("last_login", "date_joined", "onboarded_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),
    )


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("email", "code", "created_at", "expires_at", "used_at", "attempt_count")
    search_fields = ("email",)
    readonly_fields = ("id", "code", "created_at", "expires_at", "used_at", "attempt_count")
