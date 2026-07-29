from django.contrib import admin

from .models import SupportMessage, SupportThread


class SupportMessageInline(admin.TabularInline):
    model = SupportMessage
    extra = 1
    fields = ("from_admin", "body", "created_at")
    readonly_fields = ("created_at",)

    def get_formset(self, request, obj=None, **kwargs):
        # A blank reply row defaults to "from admin" — that's the only kind
        # of message added from this side of the panel.
        formset = super().get_formset(request, obj, **kwargs)
        formset.form.base_fields["from_admin"].initial = True
        return formset


@admin.register(SupportThread)
class SupportThreadAdmin(admin.ModelAdmin):
    list_display = ("user", "message_count", "last_message_at", "needs_reply", "updated_at")
    search_fields = ("user__email",)
    inlines = [SupportMessageInline]

    @admin.display(description="Messages")
    def message_count(self, obj: SupportThread) -> int:
        return obj.messages.count()

    @admin.display(description="Last message")
    def last_message_at(self, obj: SupportThread):
        last = obj.messages.last()
        return last.created_at if last else None

    @admin.display(description="Awaiting reply", boolean=True)
    def needs_reply(self, obj: SupportThread) -> bool:
        return obj.awaiting_reply
