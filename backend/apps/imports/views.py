from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .gemini import analyze_german, enrich_card, parse_text


class ParseRequestSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=20000)
    language = serializers.ChoiceField(choices=["de", "en", ""], required=False, default="")
    default_type = serializers.ChoiceField(
        choices=["vocab", "sentence", "grammar"], required=False, default="vocab"
    )


class EnrichRequestSerializer(serializers.Serializer):
    front = serializers.CharField(max_length=500)
    language = serializers.ChoiceField(choices=["de", "en", ""], required=False, default="")
    card_type = serializers.ChoiceField(
        choices=["vocab", "sentence", "grammar"], required=False, default="vocab"
    )


class AnalyzeGermanSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=1000)


class ImportParseView(APIView):
    """Parse pasted book text into draft cards (not saved). The client edits
    them, picks a deck, then commits via /api/cards/bulk/."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ParseRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = parse_text(
            serializer.validated_data["text"],
            serializer.validated_data["language"],
            serializer.validated_data["default_type"],
        )
        return Response(result, status=status.HTTP_200_OK)


class EnrichView(APIView):
    """Translate one term and fill its reading / article / example (the
    Translate button on the card editor)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EnrichRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = enrich_card(
            serializer.validated_data["front"],
            serializer.validated_data["language"],
            serializer.validated_data["card_type"],
        )
        return Response(result, status=status.HTTP_200_OK)


class AnalyzeGermanView(APIView):
    """Return each noun's true gender for a German sentence so it can be
    coloured grammatically (the "Colour genders" button)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AnalyzeGermanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(analyze_german(serializer.validated_data["text"]), status=status.HTTP_200_OK)
