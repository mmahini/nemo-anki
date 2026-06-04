from django.urls import path

from .views import AnalyzeGermanView, AnkiImportView, EnrichView, ImportParseView

urlpatterns = [
    path("import/parse/", ImportParseView.as_view(), name="import-parse"),
    path("import/enrich/", EnrichView.as_view(), name="import-enrich"),
    path("import/analyze-de/", AnalyzeGermanView.as_view(), name="import-analyze-de"),
    path("import/anki/", AnkiImportView.as_view(), name="import-anki"),
]
