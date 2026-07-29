from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path
from django.utils import timezone

from .models import Subscription, SubscriptionRequest
from .plans import MONTHLY, PLANS, QUARTERLY, YEARLY


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    change_list_template = "admin/subscriptions/subscription/change_list.html"
    list_display = ("user", "status", "live_state", "days_left", "plan", "trial_end", "current_period_end")
    list_filter = ("status", "plan")
    search_fields = ("user__email",)
    readonly_fields = ("created_at", "updated_at", "live_state", "days_left")
    actions = ["activate_monthly", "activate_quarterly", "activate_yearly", "recompute"]

    @admin.display(description="live state")
    def live_state(self, obj):
        return obj.computed_state

    @admin.display(description="days left")
    def days_left(self, obj):
        return obj.days_left

    def _activate(self, request, queryset, plan):
        for sub in queryset:
            sub.activate(plan)
        self.message_user(request, f"Activated {PLANS[plan]['label']} for {queryset.count()} user(s).")

    @admin.action(description="Activate — 1 month ($1)")
    def activate_monthly(self, request, queryset):
        self._activate(request, queryset, MONTHLY)

    @admin.action(description="Activate — 3 months ($2.50)")
    def activate_quarterly(self, request, queryset):
        self._activate(request, queryset, QUARTERLY)

    @admin.action(description="Activate — 12 months ($9)")
    def activate_yearly(self, request, queryset):
        self._activate(request, queryset, YEARLY)

    @admin.action(description="Recompute status label")
    def recompute(self, request, queryset):
        for sub in queryset:
            sub.recompute_status()
        self.message_user(request, f"Rechecked {queryset.count()} subscription(s).")

    # ---- "Check all subscriptions" button on the changelist ----
    def get_urls(self):
        custom = [
            path(
                "check-all/",
                self.admin_site.admin_view(self.check_all_view),
                name="subscriptions_subscription_check_all",
            )
        ]
        return custom + super().get_urls()

    def check_all_view(self, request):
        counts = {Subscription.TRIAL: 0, Subscription.ACTIVE: 0, Subscription.EXPIRED: 0}
        subs = list(Subscription.objects.all())
        for sub in subs:
            counts[sub.recompute_status()] += 1
        self.message_user(
            request,
            f"Checked {len(subs)} subscriptions — "
            f"{counts[Subscription.ACTIVE]} active, {counts[Subscription.TRIAL]} trial, "
            f"{counts[Subscription.EXPIRED]} expired.",
        )
        return redirect("..")


@admin.register(SubscriptionRequest)
class SubscriptionRequestAdmin(admin.ModelAdmin):
    # tx_reference is editable so an admin can add/correct the source wallet or
    # transaction hash after the user submits (or if they didn't provide one).
    list_display = ("user", "plan", "status", "tx_reference", "created_at", "reviewed_at", "reviewed_by")
    list_editable = ("tx_reference",)
    list_filter = ("status", "plan")
    search_fields = ("user__email", "tx_reference")
    readonly_fields = ("created_at", "reviewed_at", "reviewed_by")
    actions = ["approve", "reject"]

    @admin.action(description="Approve — activate the requested plan")
    def approve(self, request, queryset):
        done = 0
        for req in queryset.filter(status=SubscriptionRequest.PENDING):
            sub = Subscription.for_user(req.user)
            sub.activate(req.plan)
            req.status = SubscriptionRequest.APPROVED
            req.reviewed_at = timezone.now()
            req.reviewed_by = request.user
            req.save()
            done += 1
        self.message_user(request, f"Approved & activated {done} request(s).")

    @admin.action(description="Reject")
    def reject(self, request, queryset):
        updated = queryset.filter(status=SubscriptionRequest.PENDING).update(
            status=SubscriptionRequest.REJECTED,
            reviewed_at=timezone.now(),
            reviewed_by=request.user,
        )
        self.message_user(request, f"Rejected {updated} request(s).")
