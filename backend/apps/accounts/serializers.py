from rest_framework import serializers

from .models import OTP_LENGTH, User


class RequestOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyOTPSerializer(serializers.Serializer):
    otp_id = serializers.UUIDField()
    code = serializers.CharField(min_length=OTP_LENGTH, max_length=OTP_LENGTH)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "display_name", "ui_language", "date_joined"]
        read_only_fields = ["id", "email", "date_joined"]
