from django.urls import path

from .views import (
    AnalyzeGermanView,
    AnkiImportView,
    ConjugateView,
    EnrichView,
    ImportParseView,
    WritingCheckView,
    WritingPromptView,
    WritingToCardView,
    WritingTopicView,
)

urlpatterns = [
    path("import/parse/", ImportParseView.as_view(), name="import-parse"),
    path("import/enrich/", EnrichView.as_view(), name="import-enrich"),
    path("import/conjugate/", ConjugateView.as_view(), name="import-conjugate"),
    path("import/analyze-de/", AnalyzeGermanView.as_view(), name="import-analyze-de"),
    path("import/anki/", AnkiImportView.as_view(), name="import-anki"),
    path("writing/topic/", WritingTopicView.as_view(), name="writing-topic"),
    path("writing/check/", WritingCheckView.as_view(), name="writing-check"),
    path("writing/card/", WritingToCardView.as_view(), name="writing-card"),
    path("writing/prompt/", WritingPromptView.as_view(), name="writing-prompt"),
]
