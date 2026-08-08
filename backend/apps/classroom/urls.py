from django.urls import path

from .views import (
    ClassroomAcceptView,
    ClassroomInviteView,
    ClassroomLinkDetailView,
    MyInvitesView,
    MyStudentsView,
    MyTeachersView,
)

urlpatterns = [
    path("classroom/invite/", ClassroomInviteView.as_view(), name="classroom-invite"),
    path("classroom/students/", MyStudentsView.as_view(), name="classroom-students"),
    path("classroom/teachers/", MyTeachersView.as_view(), name="classroom-teachers"),
    path("classroom/invites/", MyInvitesView.as_view(), name="classroom-invites"),
    path("classroom/<int:pk>/accept/", ClassroomAcceptView.as_view(), name="classroom-accept"),
    path("classroom/<int:pk>/", ClassroomLinkDetailView.as_view(), name="classroom-detail"),
]
