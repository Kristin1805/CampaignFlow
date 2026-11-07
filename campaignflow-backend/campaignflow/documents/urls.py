from django.urls import path

from campaignflow.documents.apis import (
    TaskAttachmentListCreateApi, TaskAttachmentDetailApi, TaskAttachmentDownloadApi,
)

urlpatterns = [
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/attachments/", TaskAttachmentListCreateApi.as_view(), name="task-attachment-list-create",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/attachments/<uuid:attachment_id>/", TaskAttachmentDetailApi.as_view(), name="task-attachment-detail",),
    path("workspaces/<uuid:workspace_id>/tasks/<uuid:task_id>/attachments/<uuid:attachment_id>/download/", TaskAttachmentDownloadApi.as_view(), name="task-attachment-download",),
]
