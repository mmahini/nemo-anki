"""Which reels reach which user.

A reel carries two languages: the **target** (what it teaches) and the **base**
(what it's explained in). A user carries the mirror pair: `learning_languages`
and `known_languages`. A reel is a match when

    target ∈ learning_languages   AND   base ∈ known_languages

Both halves matter, and the second is the one that's easy to forget: a German
reel narrated in Persian is useless to a German learner who only reads English.
Filtering on the target alone would fill their feed with videos they can't
follow.

`base_language = ""` means immersive — German taught in German, no translation —
so there is no second language to require, and it reaches every learner of the
target.
"""

from django.db.models import Q

from .models import MEDIA_STORED, Reel


def has_language_prefs(user) -> bool:
    """False until the user has told us what they're learning. The reels feed
    asks rather than guessing: showing a Persian-narrated feed to an English
    speaker is a worse first impression than one extra question."""
    return bool(user.learning_languages)


def reel_filter(user) -> Q:
    """The match, as a Q object so callers can compose it."""
    return Q(target_language__in=user.learning_languages) & (
        Q(base_language__in=user.known_languages) | Q(base_language="")
    )


def feed_for(user):
    """Published, playable reels this user can actually follow, newest first,
    with pinned reels leading while their window is open."""
    from django.db.models import F

    return (
        Reel.objects.filter(is_published=True, media_status=MEDIA_STORED)
        .filter(reel_filter(user))
        .select_related("source")
        .order_by(F("pin_until").desc(nulls_last=True), "-posted_at", "-id")
    )


def unseen_for(user):
    return feed_for(user).exclude(views__user=user)


def default_known_languages(user) -> list[str]:
    """A sensible pre-selection for the onboarding question — someone reading
    the app in Persian almost certainly understands Persian. A default to
    confirm, never a substitute for asking."""
    return [user.ui_language] if user.ui_language else []
