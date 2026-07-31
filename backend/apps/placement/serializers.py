from rest_framework import serializers

from .models import PlacementQuestion


class StartPlacementRequestSerializer(serializers.Serializer):
    language = serializers.ChoiceField(choices=["de", "en"])
    length = serializers.ChoiceField(choices=["quick", "full"])


class PlacementQuestionOutSerializer(serializers.ModelSerializer):
    """Question shape sent to the client before grading — never includes the answer."""

    class Meta:
        model = PlacementQuestion
        fields = ["id", "order", "section", "level_tag", "passage", "audio_text", "question_text", "choices"]


class PlacementAnswerInSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    choice_index = serializers.IntegerField(min_value=0, max_value=3)


class SubmitPlacementRequestSerializer(serializers.Serializer):
    answers = PlacementAnswerInSerializer(many=True)
