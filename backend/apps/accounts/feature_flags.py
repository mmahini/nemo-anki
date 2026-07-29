"""Central registry of feature flags.

A *feature flag* is a capability string a user may hold. Flags are stored per
user (``User.feature_flags``) so they can be granted individually, and they gate
both UI visibility (exposed via the user serializer) and API access (via the
``RequiresFlag`` permission). To add a capability, add its constant here and to
``ALL_FLAGS`` — that's the single source of truth the rest of the app reads.
"""

# "staff" gates staff-only tooling — currently book upload and the My Books
# area. Seeded for existing is_staff users by migration 0003.
STAFF = "staff"

ALL_FLAGS = frozenset({STAFF})


def clean(flags) -> list[str]:
    """Keep only recognised flags, de-duplicated, order preserved."""
    return [f for f in dict.fromkeys(flags or []) if f in ALL_FLAGS]
