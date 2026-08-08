from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import ClassroomLink

User = get_user_model()


class ClassroomInviteViewTests(APITestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(email="teacher@example.com")
        self.student = User.objects.create_user(email="student@example.com")
        self.client.force_authenticate(self.teacher)
        self.url = reverse("classroom-invite")

    def test_creates_pending_link(self):
        res = self.client.post(self.url, {"email": "student@example.com"})
        self.assertEqual(res.status_code, 201)
        link = ClassroomLink.objects.get()
        self.assertEqual(res.data, {"id": link.id, "student_email": "student@example.com", "status": "pending"})
        self.assertEqual(link.teacher, self.teacher)
        self.assertEqual(link.student, self.student)

    def test_cannot_invite_self(self):
        res = self.client.post(self.url, {"email": "teacher@example.com"})
        self.assertEqual(res.status_code, 400)

    def test_cannot_invite_unknown_email(self):
        res = self.client.post(self.url, {"email": "nobody@example.com"})
        self.assertEqual(res.status_code, 404)

    def test_cannot_invite_the_same_student_twice(self):
        self.client.post(self.url, {"email": "student@example.com"})
        res = self.client.post(self.url, {"email": "student@example.com"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(ClassroomLink.objects.count(), 1)

    def test_a_teacher_can_have_many_students(self):
        other = User.objects.create_user(email="student2@example.com")
        self.client.post(self.url, {"email": "student@example.com"})
        res = self.client.post(self.url, {"email": "student2@example.com"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(ClassroomLink.objects.filter(teacher=self.teacher).count(), 2)

    def test_a_student_can_have_many_teachers(self):
        other_teacher = User.objects.create_user(email="teacher2@example.com")
        ClassroomLink.objects.create(teacher=self.teacher, student=self.student)
        self.client.force_authenticate(other_teacher)
        res = self.client.post(self.url, {"email": "student@example.com"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(ClassroomLink.objects.filter(student=self.student).count(), 2)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self.client.post(self.url, {"email": "student@example.com"})
        self.assertEqual(res.status_code, 401)


class MyStudentsViewTests(APITestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(email="teacher@example.com")
        self.student = User.objects.create_user(email="student@example.com")
        self.client.force_authenticate(self.teacher)
        self.url = reverse("classroom-students")

    def test_lists_pending_and_accepted_students(self):
        ClassroomLink.objects.create(teacher=self.teacher, student=self.student, status="pending")
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["status"], "pending")
        self.assertIsNone(res.data[0]["student"])

    def test_accepted_student_includes_streak_summary(self):
        ClassroomLink.objects.create(teacher=self.teacher, student=self.student, status="accepted")
        res = self.client.get(self.url)
        self.assertEqual(res.data[0]["student"], {"today": 0, "streak": 0})

    def test_does_not_list_links_from_other_teachers(self):
        other_teacher = User.objects.create_user(email="teacher2@example.com")
        ClassroomLink.objects.create(teacher=other_teacher, student=self.student, status="accepted")
        res = self.client.get(self.url)
        self.assertEqual(res.data, [])

    def test_requires_authentication(self):
        self.client.force_authenticate(None)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 401)


class MyTeachersViewTests(APITestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(email="teacher@example.com")
        self.student = User.objects.create_user(email="student@example.com")
        self.client.force_authenticate(self.student)
        self.url = reverse("classroom-teachers")

    def test_lists_accepted_teachers_only(self):
        ClassroomLink.objects.create(teacher=self.teacher, student=self.student, status="pending")
        res = self.client.get(self.url)
        self.assertEqual(res.data, [])

    def test_lists_accepted_teacher(self):
        link = ClassroomLink.objects.create(teacher=self.teacher, student=self.student, status="accepted")
        res = self.client.get(self.url)
        self.assertEqual(res.data, [{"id": link.id, "teacher_email": "teacher@example.com"}])


class MyInvitesViewTests(APITestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(email="teacher@example.com")
        self.student = User.objects.create_user(email="student@example.com")
        self.client.force_authenticate(self.student)
        self.url = reverse("classroom-invites")

    def test_lists_pending_invites(self):
        link = ClassroomLink.objects.create(teacher=self.teacher, student=self.student)
        res = self.client.get(self.url)
        self.assertEqual(res.data, [{"id": link.id, "teacher_email": "teacher@example.com"}])

    def test_excludes_accepted_links(self):
        ClassroomLink.objects.create(teacher=self.teacher, student=self.student, status="accepted")
        res = self.client.get(self.url)
        self.assertEqual(res.data, [])

    def test_can_have_invites_from_multiple_teachers(self):
        other_teacher = User.objects.create_user(email="teacher2@example.com")
        ClassroomLink.objects.create(teacher=self.teacher, student=self.student)
        ClassroomLink.objects.create(teacher=other_teacher, student=self.student)
        res = self.client.get(self.url)
        self.assertEqual(len(res.data), 2)


class ClassroomAcceptViewTests(APITestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(email="teacher@example.com")
        self.student = User.objects.create_user(email="student@example.com")

    def test_student_can_accept(self):
        link = ClassroomLink.objects.create(teacher=self.teacher, student=self.student)
        self.client.force_authenticate(self.student)
        res = self.client.post(reverse("classroom-accept", args=[link.id]))
        self.assertEqual(res.status_code, 200)
        link.refresh_from_db()
        self.assertEqual(link.status, "accepted")
        self.assertIsNotNone(link.responded_at)

    def test_teacher_cannot_accept_their_own_invite(self):
        link = ClassroomLink.objects.create(teacher=self.teacher, student=self.student)
        self.client.force_authenticate(self.teacher)
        res = self.client.post(reverse("classroom-accept", args=[link.id]))
        self.assertEqual(res.status_code, 404)

    def test_another_student_cannot_accept(self):
        link = ClassroomLink.objects.create(teacher=self.teacher, student=self.student)
        stranger = User.objects.create_user(email="stranger@example.com")
        self.client.force_authenticate(stranger)
        res = self.client.post(reverse("classroom-accept", args=[link.id]))
        self.assertEqual(res.status_code, 404)

    def test_404_for_unknown_link(self):
        self.client.force_authenticate(self.student)
        res = self.client.post(reverse("classroom-accept", args=[999]))
        self.assertEqual(res.status_code, 404)


class ClassroomLinkDetailViewTests(APITestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(email="teacher@example.com")
        self.student = User.objects.create_user(email="student@example.com")

    def test_teacher_can_remove_a_student(self):
        link = ClassroomLink.objects.create(teacher=self.teacher, student=self.student, status="accepted")
        self.client.force_authenticate(self.teacher)
        res = self.client.delete(reverse("classroom-detail", args=[link.id]))
        self.assertEqual(res.status_code, 204)
        self.assertFalse(ClassroomLink.objects.exists())

    def test_student_can_leave(self):
        link = ClassroomLink.objects.create(teacher=self.teacher, student=self.student, status="accepted")
        self.client.force_authenticate(self.student)
        res = self.client.delete(reverse("classroom-detail", args=[link.id]))
        self.assertEqual(res.status_code, 204)
        self.assertFalse(ClassroomLink.objects.exists())

    def test_a_stranger_cannot_remove_the_link(self):
        link = ClassroomLink.objects.create(teacher=self.teacher, student=self.student, status="accepted")
        stranger = User.objects.create_user(email="stranger@example.com")
        self.client.force_authenticate(stranger)
        res = self.client.delete(reverse("classroom-detail", args=[link.id]))
        self.assertEqual(res.status_code, 404)
        self.assertTrue(ClassroomLink.objects.exists())

    def test_requires_authentication(self):
        link = ClassroomLink.objects.create(teacher=self.teacher, student=self.student)
        res = self.client.delete(reverse("classroom-detail", args=[link.id]))
        self.assertEqual(res.status_code, 401)
