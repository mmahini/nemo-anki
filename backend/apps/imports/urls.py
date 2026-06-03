from django.urls import path

from .views import ImportParseView

urlpatterns = [
    path("import/parse/", ImportParseView.as_view(), name="import-parse"),
]
