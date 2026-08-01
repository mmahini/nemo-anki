from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .email import send_otp_email
from .models import EmailOTP, User
from .serializers import RequestOTPSerializer, UserSerializer, VerifyOTPSerializer


def _tokens_for(user: User) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _apply_referral(user: User, code: str) -> bool:
    """Link a brand-new account to its inviter and gift the signup reward
    (a month of Basic). Quietly a no-op on an unknown or own code — a stale
    invite link must never block signing up."""
    code = (code or "").strip()
    if not code:
        return False
    referrer = User.objects.filter(referral_code=code).exclude(pk=user.pk).first()
    if referrer is None:
        return False
    user.referred_by = referrer
    user.save(update_fields=["referred_by"])
    # Imported lazily to keep accounts decoupled from the subscriptions app.
    from apps.subscriptions.models import Subscription
    from apps.subscriptions.plans import REFERRAL_BONUS_DAYS, REFERRAL_BONUS_TIER

    Subscription.for_user(user).grant_bonus(REFERRAL_BONUS_TIER, days=REFERRAL_BONUS_DAYS)
    return True


@method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=True), name="post")
@method_decorator(ratelimit(key="post:email", rate="10/h", method="POST", block=True), name="post")
class RequestOTPView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        serializer = RequestOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()

        otp = EmailOTP.issue(email=email)

        emailed = send_otp_email(email, otp.code)
        payload = {
            "otp_id": str(otp.id),
            "expires_at": otp.expires_at.isoformat(),
            "emailed": emailed,
        }
        # Only surface the code when we couldn't email it (local dev / no key),
        # so production never leaks codes in the API response.
        if not emailed:
            payload["dev_code"] = otp.code
        return Response(payload, status=status.HTTP_201_CREATED)


@method_decorator(ratelimit(key="ip", rate="10/m", method="POST", block=True), name="post")
class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp_id = serializer.validated_data["otp_id"]
        code = serializer.validated_data["code"]

        try:
            otp = EmailOTP.objects.get(id=otp_id)
        except EmailOTP.DoesNotExist:
            return Response({"detail": "OTP not found."}, status=status.HTTP_404_NOT_FOUND)

        if otp.is_used:
            return Response({"detail": "OTP already used."}, status=status.HTTP_410_GONE)
        if otp.is_expired:
            return Response({"detail": "OTP expired."}, status=status.HTTP_410_GONE)
        if otp.is_locked:
            return Response({"detail": "Too many attempts."}, status=status.HTTP_403_FORBIDDEN)

        if otp.code != code:
            otp.register_failed_attempt()
            remaining = max(0, 5 - otp.attempt_count)
            return Response(
                {"detail": "Incorrect code.", "attempts_remaining": remaining},
                status=status.HTTP_400_BAD_REQUEST,
            )

        otp.mark_used()
        user, created = User.objects.get_or_create(email=otp.email)
        # Referral only counts at account creation — signing back in through an
        # invite link must not hand out another month.
        referral_applied = created and _apply_referral(
            user, serializer.validated_data.get("referral_code", "")
        )
        return Response(
            {
                **_tokens_for(user),
                "user": UserSerializer(user).data,
                # First-ever verification creates the account; the client uses
                # this to emit a one-time Wiser CDP `signup` event.
                "is_new_user": created,
                # The invite reward was granted — the client tells the user in
                # the welcome flow.
                "referral_applied": referral_applied,
            },
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
