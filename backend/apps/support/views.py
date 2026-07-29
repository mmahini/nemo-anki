from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SupportMessage, SupportThread
from .serializers import SupportThreadSerializer


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
        SupportMessage.objects.create(thread=thread, body=body)
        thread.save(update_fields=["updated_at"])
        return Response(SupportThreadSerializer(thread).data, status=status.HTTP_201_CREATED)
