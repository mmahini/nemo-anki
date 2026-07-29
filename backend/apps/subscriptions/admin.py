from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path
from django.utils import timezone

from .models import Subscription, SubscriptionRequest
from .plans import PLANS, TIERS


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    change_list_template = "admin/subscriptions/subscription/change_list.html"
    list_display = ("user", "status", "live_state", "tier", "ai_limit", "days_left", "plan", "current_period_end")
    list_filter = ("status", "tier", "plan")
    search_fields = ("user__email",)
    readonly_fields = ("created_at", "updated_at", "live_state", "ai_limit", "days_left")
    actions = [
        "activate_basic_monthly", "activate_basic_quarterly", "activate_basic_yearly",
        "activate_pro_monthly", "activate_pro_quarterly", "activate_pro_yearly",
        "recompute",
    ]

    @admin.display(description="live state")
    def live_state(self, obj):
        return obj.computed_state

    @admin.display(description="AI/day")
    def ai_limit(self, obj):
        return obj.daily_ai_limit

    @admin.display(description="days left")
    def days_left(self, obj):
        return obj.days_left

    def _activate(self, request, queryset, plan):
        for sub in queryset:
            sub.activate(plan)
        tier = TIERS[PLANS[plan]["tier"]]["label"]
        self.message_user(request, f"Activated {tier} · {PLANS[plan]['label']} for {queryset.count()} user(s).")

    @admin.action(description="Activate — Basic · 1 month ($1)")
    def activate_basic_monthly(self, request, queryset):
        self._activate(request, queryset, "basic_monthly")

    @admin.action(description="Activate — Basic · 3 months ($2.50)")
    def activate_basic_quarterly(self, request, queryset):
        self._activate(request, queryset, "basic_quarterly")

    @admin.action(description="Activate — Basic · 12 months ($9)")
    def activate_basic_yearly(self, request, queryset):
        self._activate(request, queryset, "basic_yearly")

    @admin.action(description="Activate — Pro · 1 month ($5)")
    def activate_pro_monthly(self, request, queryset):
        self._activate(request, queryset, "pro_monthly")

    @admin.action(description="Activate — Pro · 3 months ($12.50)")
    def activate_pro_quarterly(self, request, queryset):
        self._activate(request, queryset, "pro_quarterly")

    @admin.action(description="Activate — Pro · 12 months ($45)")
    def activate_pro_yearly(self, request, queryset):
        self._activate(request, queryset, "pro_yearly")

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
