from django.db import models


class ClassroomLink(models.Model):
    """A teacher watching a student's progress — one-to-many and asymmetric
    (a teacher can have many students; a student can have many teachers),
    unlike the mutual, singular apps.buddy.BuddyLink. Needs the student's
    acceptance, same consent principle as buddy pairing."""

    STATUS_CHOICES = [("pending", "Pending"), ("accepted", "Accepted")]

    teacher = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="classroom_students"
    )
    student = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="classroom_teachers"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["teacher", "student"], name="unique_classroom_link"),
        ]

    def __str__(self) -> str:
        return f"{self.teacher_id} watches {self.student_id} ({self.status})"
