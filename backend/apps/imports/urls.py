from django.urls import path

from .views import EnrichView, ImportParseView

urlpatterns = [
    path("import/parse/", ImportParseView.as_view(), name="import-parse"),
    path("import/enrich/", EnrichView.as_view(), name="import-enrich"),
]
