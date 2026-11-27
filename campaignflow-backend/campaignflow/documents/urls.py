from django.urls import path

from campaignflow.documents.apis import (
    TaskAttachmentListCreateApi,
    TaskAttachmentDetailApi,
    TaskAttachmentDownloadApi,
    DocumentTemplateListApi,
    DocumentTemplateCategoriesApi,
    DocumentTemplatePlaceholdersApi,
    DocumentTemplateSchemaApi,
    DocumentTemplateDraftApi,
    DocumentTemplateDetailsApi,
    DocumentTemplatePublishApi,
    DocumentTemplateVersionListApi,
    DocumentTemplateVersionRestoreApi,
    DocumentTemplateVersionDetailsApi,
    DocumentTemplateDuplicateApi,
    DocumentTemplateRestoreApi,
    DocumentTemplateArchiveApi,
    DocumentListApi,
    DocumentDetailsApi,
    DocumentGenerateApi,
    DocumentGenerationPreviewApi,
    DocumentBlankApi,
    DocumentDuplicateApi,
    DocumentStatusApi,
    DocumentArchiveApi,
    DocumentRestoreApi,
)

PREFIX = "workspaces/<uuid:workspace_id>/document-templates/"
DOCUMENT_PREFIX = "workspaces/<uuid:workspace_id>/documents/"


urlpatterns = [
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/attachments/", TaskAttachmentListCreateApi.as_view(), name="task-attachment-list-create",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/attachments/<uuid:attachment_id>/", TaskAttachmentDetailApi.as_view(), name="task-attachment-detail",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/attachments/<uuid:attachment_id>/download/", TaskAttachmentDownloadApi.as_view(), name="task-attachment-download",),
    path(PREFIX, DocumentTemplateListApi.as_view(), name="document-template-list"),
    path(PREFIX + "categories/", DocumentTemplateCategoriesApi.as_view(), name="document-template-categories"),
    path(PREFIX + "placeholders/", DocumentTemplatePlaceholdersApi.as_view(), name="document-template-placeholders"),
    path(PREFIX + "schema/", DocumentTemplateSchemaApi.as_view(), name="document-template-schema"),
    path(PREFIX + "<uuid:template_id>/", DocumentTemplateDetailsApi.as_view(), name="document-template-details"),
    path(PREFIX + "<uuid:template_id>/draft/", DocumentTemplateDraftApi.as_view(), name="document-template-draft"),
    path(PREFIX + "<uuid:template_id>/publish/", DocumentTemplatePublishApi.as_view(), name="document-template-publish"),
    path(PREFIX + "<uuid:template_id>/versions/", DocumentTemplateVersionListApi.as_view(), name="document-template-versions"),
    path(PREFIX + "<uuid:template_id>/versions/<uuid:version_id>/", DocumentTemplateVersionDetailsApi.as_view(), name="document-template-version-details"),
    path(PREFIX + "<uuid:template_id>/versions/<uuid:version_id>/restore/", DocumentTemplateVersionRestoreApi.as_view(), name="document-template-version-restore"),
    path(PREFIX + "<uuid:template_id>/duplicate/", DocumentTemplateDuplicateApi.as_view(), name="document-template-duplicate"),
    path(PREFIX + "<uuid:template_id>/archive/", DocumentTemplateArchiveApi.as_view(), name="document-template-archive"),
    path(PREFIX + "<uuid:template_id>/restore/", DocumentTemplateRestoreApi.as_view(), name="document-template-restore"),

    path(DOCUMENT_PREFIX, DocumentListApi.as_view(), name="document-list"),
    path(DOCUMENT_PREFIX + "generate/", DocumentGenerateApi.as_view(), name="document-generate"),
    path(DOCUMENT_PREFIX + "generate/preview/", DocumentGenerationPreviewApi.as_view(), name="document-generation-preview"),
    path(DOCUMENT_PREFIX + "blank/", DocumentBlankApi.as_view(), name="document-blank"),
    path(DOCUMENT_PREFIX + "<uuid:document_id>/", DocumentDetailsApi.as_view(), name="document-details"),
    path(DOCUMENT_PREFIX + "<uuid:document_id>/duplicate/", DocumentDuplicateApi.as_view(), name="document-duplicate"),
    path(DOCUMENT_PREFIX + "<uuid:document_id>/status/", DocumentStatusApi.as_view(), name="document-status"),
    path(DOCUMENT_PREFIX + "<uuid:document_id>/archive/", DocumentArchiveApi.as_view(), name="document-archive"),
    path(DOCUMENT_PREFIX + "<uuid:document_id>/restore/", DocumentRestoreApi.as_view(), name="document-restore"),

    path(
        "workspaces/<uuid:workspace_id>/campaigns/<uuid:campaign_id>/documents/",
        DocumentListApi.as_view(),
        name="campaign-document-list",
    ),
]