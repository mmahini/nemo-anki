from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cards.activity import streak_summary

from .models import ClassroomLink

User = get_user_model()


class ClassroomInviteView(APIView):
    """A teacher invites a student by email — inert until the student
    accepts (see ClassroomAcceptView), same consent principle as
    apps.buddy. Unlike buddy pairing, a teacher may have any number of
    students and a student any number of teachers; the only limit is one
    link per (teacher, student) pair (unique_classroom_link)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return Response({"detail": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
        if email == request.user.email.lower():
            return Response({"detail": "That's you."}, status=status.HTTP_400_BAD_REQUEST)
        target = User.objects.filter(email=email).first()
        if not target:
            return Response({"detail": "No user with that email yet."}, status=status.HTTP_404_NOT_FOUND)
        if ClassroomLink.objects.filter(teacher=request.user, student=target).exists():
            return Response(
                {"detail": "You've already invited this student."}, status=status.HTTP_400_BAD_REQUEST
            )
        link = ClassroomLink.objects.create(teacher=request.user, student=target)
        return Response(
            {"id": link.id, "student_email": target.email, "status": "pending"},
            status=status.HTTP_201_CREATED,
        )


class MyStudentsView(APIView):
    """A teacher's roster: everyone they've invited, pending or accepted,
    with today/streak once accepted."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        links = ClassroomLink.objects.filter(teacher=request.user).select_related("student")
        return Response(
            [
                {
                    "id": link.id,
                    "student_email": link.student.email,
                    "status": link.status,
                    "student": streak_summary(link.student) if link.status == "accepted" else None,
                }
                for link in links
            ]
        )


class MyTeachersView(APIView):
    """The consent-transparency view: everyone currently watching this
    user's progress — always available so a student can see (and revoke,
    via ClassroomLinkDetailView) who has access."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        links = ClassroomLink.objects.filter(student=request.user, status="accepted").select_related("teacher")
        return Response([{"id": link.id, "teacher_email": link.teacher.email} for link in links])


class MyInvitesView(APIView):
    """A student's pending incoming invites — unlike apps.buddy there can
    be several at once, from different teachers."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        links = ClassroomLink.objects.filter(student=request.user, status="pending").select_related("teacher")
        return Response([{"id": link.id, "teacher_email": link.teacher.email} for link in links])


class ClassroomAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        link = ClassroomLink.objects.filter(pk=pk, student=request.user, status="pending").first()
        if not link:
            return Response({"detail": "No pending invite to accept."}, status=status.HTTP_404_NOT_FOUND)
        link.status = "accepted"
        link.responded_at = timezone.now()
        link.save(update_fields=["status", "responded_at"])
        return Response({"id": link.id, "teacher_email": link.teacher.email})


class ClassroomLinkDetailView(APIView):
    """Either side of a link can remove it: the teacher drops a student, or
    the student declines an invite / leaves an accepted classroom."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        deleted, _ = ClassroomLink.objects.filter(
            Q(pk=pk) & (Q(teacher=request.user) | Q(student=request.user))
        ).delete()
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
