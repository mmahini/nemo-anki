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

from . import matching
from .models import Reel, ReelView
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

        qs = matching.feed_for(user) if include_seen else matching.unseen_for(user)
        page = list(qs[offset : offset + PAGE_SIZE])

        # Caught up: rather than an empty feed, replay the library oldest-seen
        # first so there's always something to watch.
        exhausted = False
        if not page and not include_seen and offset == 0:
            exhausted = True
            page = list(matching.feed_for(user)[:PAGE_SIZE])

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
