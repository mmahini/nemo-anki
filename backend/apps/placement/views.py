from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.subscriptions.quota import AiQuotaMixin

from .gemini import generate_placement_questions
from .models import PlacementAttempt, PlacementQuestion
from .scoring import estimate_level
from .serializers import (
    PlacementQuestionOutSerializer,
    StartPlacementRequestSerializer,
    SubmitPlacementRequestSerializer,
)


class StartPlacementView(AiQuotaMixin, APIView):
    """Generate an original Reading + Listening placement test and start an attempt."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = StartPlacementRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        language = serializer.validated_data["language"]
        length = serializer.validated_data["length"]

        questions = generate_placement_questions(language, length)

        attempt = PlacementAttempt.objects.create(
            user=request.user, language=language, length=length, total_count=len(questions)
        )
        PlacementQuestion.objects.bulk_create(
            PlacementQuestion(
                attempt=attempt,
                order=i,
                section=q["section"],
                level_tag=q["level"],
                passage=q["text"] if q["section"] == "reading" else "",
                audio_text=q["text"] if q["section"] == "listening" else "",
                question_text=q["question"],
                choices=q["choices"],
                correct_choice_index=q["correct_index"],
            )
            for i, q in enumerate(questions)
        )

        out = PlacementQuestionOutSerializer(attempt.questions.order_by("order"), many=True).data
        return Response({"attempt_id": attempt.id, "questions": out}, status=status.HTTP_201_CREATED)


class SubmitPlacementView(APIView):
    """Grade a completed attempt (pure DB work — no Gemini call, no AI quota)."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        serializer = SubmitPlacementRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        attempt = PlacementAttempt.objects.filter(pk=pk, user=request.user).first()
        if not attempt:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if attempt.status == "completed":
            return Response({"detail": "Already submitted."}, status=status.HTTP_400_BAD_REQUEST)

        answers = {
            a["question_id"]: a["choice_index"] for a in serializer.validated_data["answers"]
        }
        questions = list(attempt.questions.all())

        results = []
        correct_count = 0
        for q in questions:
            choice = answers.get(q.id)
            is_correct = choice is not None and choice == q.correct_choice_index
            correct_count += is_correct
            q.user_choice_index = choice
            results.append({"level_tag": q.level_tag, "is_correct": is_correct})
        PlacementQuestion.objects.bulk_update(questions, ["user_choice_index"])

        by_level: dict[str, dict[str, int]] = {}
        for r in results:
            slot = by_level.setdefault(r["level_tag"], {"correct": 0, "total": 0})
            slot["total"] += 1
            slot["correct"] += r["is_correct"]

        attempt.correct_count = correct_count
        attempt.total_count = len(questions)
        attempt.estimated_level = estimate_level(results)
        attempt.status = "completed"
        attempt.completed_at = timezone.now()
        attempt.save(
            update_fields=["correct_count", "total_count", "estimated_level", "status", "completed_at"]
        )

        # Provision the starter decks now (idempotent — a no-op if the user
        # already has them) and point the result at the one matching this
        # result, so "back to my decks" lands the learner on material at
        # their level instead of an empty deck list.
        from apps.cards.seeding import find_level_deck, seed_for_user

        seed_for_user(request.user)
        deck = find_level_deck(request.user, attempt.language, attempt.estimated_level)

        return Response(
            {
                "estimated_level": attempt.estimated_level,
                "correct_count": correct_count,
                "total_count": len(questions),
                "by_level": by_level,
                "deck_id": deck.id if deck else None,
            }
        )
