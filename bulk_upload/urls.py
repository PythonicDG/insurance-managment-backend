from django.urls import path

from .views import ImportView, PreviewView, TemplateDownloadView, TemplateListView

urlpatterns = [
    path("templates/", TemplateListView.as_view(), name="bulk-upload-templates"),
    path("templates/<int:pk>/download/", TemplateDownloadView.as_view(), name="bulk-upload-template-download"),
    path("preview/", PreviewView.as_view(), name="bulk-upload-preview"),
    path("import/", ImportView.as_view(), name="bulk-upload-import"),
]
