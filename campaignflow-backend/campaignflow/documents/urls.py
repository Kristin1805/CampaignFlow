from django.urls import path

from campaignflow.documents.apis import (
    TaskAttachmentListCreateApi, TaskAttachmentDetailApi, TaskAttachmentDownloadApi, DocumentTemplateListApi,
    DocumentTemplateCategoriesApi, DocumentTemplatePlaceholdersApi, DocumentTemplateSchemaApi, DocumentTemplateDraftApi,
    DocumentTemplateDetailsApi, DocumentTemplatePublishApi, DocumentTemplateVersionListApi,
    DocumentTemplateVersionRestoreApi, DocumentTemplateVersionDetailsApi, DocumentTemplateDuplicateApi,
    DocumentTemplateRestoreApi, DocumentTemplateArchiveApi,
)

PREFIX = "workspaces/<uuid:workspace_id>/document-templates/"


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
    path(PREFIX + "<uuid:template_id>/versions/<uuid:version_id>/", DocumentTemplateVersionDetailsApi.as_view(),name="document-template-version-details",),
    path(PREFIX + "<uuid:template_id>/versions/<uuid:version_id>/restore/", DocumentTemplateVersionRestoreApi.as_view(),name="document-template-version-restore",),
    path(PREFIX + "<uuid:template_id>/duplicate/", DocumentTemplateDuplicateApi.as_view(), name="document-template-duplicate"),
    path(PREFIX + "<uuid:template_id>/archive/", DocumentTemplateArchiveApi.as_view(), name="document-template-archive"),
    path(PREFIX + "<uuid:template_id>/restore/", DocumentTemplateRestoreApi.as_view(), name="document-template-restore"),
]