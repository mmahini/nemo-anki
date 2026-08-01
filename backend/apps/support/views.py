from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PushSubscription, SupportMessage, SupportThread
from .notifications import notify_staff_of_message
from .serializers import PushSubscriptionSerializer, SupportThreadSerializer


class SupportThreadView(APIView):
    """The user's single running support conversation — created on first use."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        thread, _ = SupportThread.objects.get_or_create(user=request.user)
        return Response(SupportThreadSerializer(thread).data)

    def post(self, request):
        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"detail": "Message can't be empty."}, status=status.HTTP_400_BAD_REQUEST)
        thread, _ = SupportThread.objects.get_or_create(user=request.user)
        message = SupportMessage.objects.create(thread=thread, body=body)
        thread.save(update_fields=["updated_at"])
        notify_staff_of_message(thread, message)
        return Response(SupportThreadSerializer(thread).data, status=status.HTTP_201_CREATED)


class PushSubscribeView(APIView):
    """Register/unregister a staff member's browser as a push target for new
    support messages. Only staff subscribe — the alert is for whoever answers
    support, not regular users."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)
        serializer = PushSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        PushSubscription.objects.update_or_create(
            endpoint=data["endpoint"],
            defaults={
                "user": request.user,
                "p256dh": data["keys"]["p256dh"],
                "auth": data["keys"]["auth"],
            },
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request):
        endpoint = (request.data.get("endpoint") or "").strip()
        if endpoint:
            PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
