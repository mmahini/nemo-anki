"""The user-facing Reels API.

The feed's whole job is to hand back reels this user can actually follow —
right target language, and an explanation language they read (see
apps.reels.matching). When we've never asked them, it says so instead of
guessing, because a guessed feed is worse than one extra question.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import re

from apps.accounts.languages import LANGUAGES
from apps.subscriptions.quota import consume_ai_quota

from . import cards, matching
from .models import Reel, ReelSource, ReelSourceSuggestion, ReelView
from .serializers import ReelSerializer

PAGE_SIZE = 12


def _saved_ids(user, reels) -> set[int]:
    return set(
        ReelView.objects.filter(user=user, saved=True, reel__in=reels).values_list(
            "reel_id", flat=True
        )
    )


class ReelFeedView(APIView):
    """GET /api/reels/ — the unseen feed, newest first, pinned reels leading.

    `?offset=` pages through it. `?all=1` includes reels already seen, which is
    also what we fall back to once someone reaches the end: an empty screen
    reads like a broken feature, a re-run of older reels reads like a library.

    `?lang=de` narrows the feed to one target language. Someone learning both
    English and German gets a per-language feed the client can switch between
    — mixing the two in one scroll reads as noise, not variety. Only languages
    the user is actually learning are honoured; anything else is ignored
    rather than 400'd (a stale client shouldn't break the feed).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not matching.has_language_prefs(user):
            # Not a failure — the client renders the language picker.
            return Response(
                {
                    "needs_language_prefs": True,
                    "results": [],
                    "suggested_known_languages": matching.default_known_languages(user),
                }
            )

        offset = max(int(request.query_params.get("offset") or 0), 0)
        include_seen = request.query_params.get("all") == "1"
        lang = (request.query_params.get("lang") or "").strip()
        if lang not in user.learning_languages:
            lang = ""

        def narrowed(qs):
            return qs.filter(target_language=lang) if lang else qs

        qs = narrowed(matching.feed_for(user) if include_seen else matching.unseen_for(user))
        page = list(qs[offset : offset + PAGE_SIZE])

        # Caught up: rather than an empty feed, replay the library oldest-seen
        # first so there's always something to watch. Still per-language — the
        # replay answers "show me more German", not "show me anything".
        exhausted = False
        if not page and not include_seen and offset == 0:
            exhausted = True
            page = list(narrowed(matching.feed_for(user))[:PAGE_SIZE])

        data = ReelSerializer(
            page,
            many=True,
            context={"saved_ids": _saved_ids(user, page), "request": request},
        ).data
        return Response(
            {
                "needs_language_prefs": False,
                "results": data,
                "next_offset": offset + len(page) if len(page) == PAGE_SIZE else None,
                "caught_up": exhausted,
            }
        )


class ReelSeenView(APIView):
    """POST /api/reels/<pk>/seen/ — idempotent; the client fires it freely."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        reel = Reel.objects.filter(pk=pk).first()
        if reel is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        ReelView.objects.get_or_create(user=request.user, reel=reel)
        return Response({"ok": True})


class ReelSaveView(APIView):
    """POST /api/reels/<pk>/save/ — toggles. Saved reels are also exempt from
    the retention purge, so this is a promise we keep."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        reel = Reel.objects.filter(pk=pk).first()
        if reel is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        view, _ = ReelView.objects.get_or_create(user=request.user, reel=reel)
        view.saved = not view.saved
        view.save(update_fields=["saved"])
        return Response({"saved": view.saved})


class ReelMakeCardsView(APIView):
    """POST /api/reels/<pk>/make-cards/ — turn watching into a deck.

    Three tiers, cheapest first:
      1. The user already materialised this reel → return their deck. Free.
      2. Staff linked a curated deck → plain deep copy. Free (no AI involved).
      3. AI path: one unit of the user's daily quota is consumed **whether or
         not the drafts are already cached** — the cache saves our Gemini
         bill, not the user's quota; they receive the same value either way.
         Generation itself runs once per reel and is cached on the row.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        reel = (
            Reel.objects.filter(pk=pk, is_published=True)
            .select_related("source", "linked_deck")
            .first()
        )
        if reel is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if reel.linked_deck_id:
            from apps.decks.sharing import copy_deck_tree

            deck = copy_deck_tree(reel.linked_deck, request.user, wrapper_name=cards.WRAPPER_NAME)
            return Response({"deck": deck.id}, status=status.HTTP_201_CREATED)

        existing = cards.existing_deck_for(reel, request.user)
        if existing is not None:
            return Response({"deck": existing.id})

        consume_ai_quota(request.user)  # raises 429 over the daily limit
        drafts = cards.ensure_drafts(reel)
        if not drafts:
            return Response(
                {"detail": "Couldn't build cards from this reel."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        deck = cards.materialize(reel, request.user, drafts)
        return Response({"deck": deck.id}, status=status.HTTP_201_CREATED)


class ReelUnseenCountView(APIView):
    """GET /api/reels/unseen-count/ — how many matching reels this user hasn't
    watched. Powers the home-page "new reels" card; a plain count so the home
    screen never pays for a full feed serialisation it won't render."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not matching.has_language_prefs(user):
            # The card still renders as a doorway; there's just nothing to count.
            return Response({"count": 0})
        return Response({"count": matching.unseen_for(user).count()})


_IG_USERNAME = re.compile(r"^[a-z0-9._]{1,30}$")


class ReelSuggestSourceView(APIView):
    """POST /api/reels/suggest-source/ — "please add this Instagram account".

    Lands as a ReelSourceSuggestion for staff review; an admin action turns it
    into a real ReelSource. Suggesting an account we already watch, or one the
    user already suggested, answers honestly instead of stacking duplicates.
    """

    permission_classes = [IsAuthenticated]

    DAILY_CAP = 5  # a hand-typed form doesn't need more; a script shouldn't get more

    def post(self, request):
        username = (request.data.get("username") or "").strip().lstrip("@").lower()
        # Instagram usernames: letters, digits, dots, underscores.
        if not _IG_USERNAME.match(username):
            return Response(
                {"detail": "That doesn't look like an Instagram username."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target = request.data.get("target_language") or ""
        base = request.data.get("base_language") or ""
        if target not in LANGUAGES or (base and base not in LANGUAGES):
            return Response(
                {"detail": "Unknown language."}, status=status.HTTP_400_BAD_REQUEST
            )

        if ReelSource.objects.filter(username=username).exists():
            return Response({"status": "exists"})
        if ReelSourceSuggestion.objects.filter(
            user=request.user, username=username, status="pending"
        ).exists():
            return Response({"status": "pending"})

        from django.utils import timezone

        today = timezone.now().date()
        if (
            ReelSourceSuggestion.objects.filter(
                user=request.user, created_at__date=today
            ).count()
            >= self.DAILY_CAP
        ):
            return Response(
                {"detail": "That's plenty of suggestions for one day — thank you!"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        ReelSourceSuggestion.objects.create(
            user=request.user,
            username=username,
            target_language=target,
            base_language=base,
        )
        return Response({"status": "ok"}, status=status.HTTP_201_CREATED)


class ReelSavedListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        reels = list(
            Reel.objects.filter(views__user=request.user, views__saved=True)
            .select_related("source")
            .order_by("-views__seen_at")
        )
        data = ReelSerializer(
            reels,
            many=True,
            context={"saved_ids": {r.id for r in reels}, "request": request},
        ).data
        return Response({"results": data})
