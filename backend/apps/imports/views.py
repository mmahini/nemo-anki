from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .gemini import parse_text


class ParseRequestSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=20000)
    language = serializers.ChoiceField(choices=["de", "en", ""], required=False, default="")
    default_type = serializers.ChoiceField(
        choices=["vocab", "sentence", "grammar"], required=False, default="vocab"
    )


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
