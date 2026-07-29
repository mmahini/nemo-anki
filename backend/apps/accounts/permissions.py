from rest_framework.permissions import IsAuthenticated


def RequiresFlag(flag: str):
    """Permission class factory: authenticated AND holds the given feature flag.

    Usage: ``permission_classes = [RequiresFlag("staff")]`` or, per-method,
    ``get_permissions`` returning ``[RequiresFlag("staff")()]``.
    """

    class _RequiresFlag(IsAuthenticated):
        message = f"This feature requires the '{flag}' flag."

        def has_permission(self, request, view) -> bool:
            return super().has_permission(request, view) and request.user.has_flag(flag)

    return _RequiresFlag
